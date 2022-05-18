from pyexpat import features
import cv2
import numpy as np
import pandas as pd
import sys
import os


import json
# import torch
# import torchvision.models as models
# import torchvision.transforms as transforms
import scipy
import time

from PIL import Image
from torch.autograd import Variable as V

from util import resize_with_aspectratio
from util import printProgressBar

import tensorflow as tf
from keras.applications.imagenet_utils import decode_predictions, preprocess_input
from keras.models import Model
from tensorflow.keras.applications.vgg16 import VGG16
from scipy.spatial import distance
from keras.preprocessing import image


# class CustomResNet():
#     def __init__(self):
#         self.model = models.resnet18()
#         self.model.eval()
    
#     def get_feature_vector(self, img_path):
#         # https://towardsdatascience.com/recommending-similar-images-using-pytorch-da019282770c

#         feature_layer = self.model.avgpool
#         feature_vector = torch.zeros(1, 512, 1, 1)

#         # Define image manipulations and process image using standard ResNet parameters.
#         img = Image.open(img_path) if isinstance(img_path, str) else Image.fromarray(img_path)
#         centre_crop = transforms.Compose([
#             # #transforms.Resize((224,224)),
#             # transforms.CenterCrop(224),
#             # #transforms.RandomResizedCrop(224),
#             # transforms.ToTensor(),
#             # transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

#             transforms.Resize(224),
#             #transforms.CenterCrop(224),
#             transforms.ToTensor(),
#             transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
#         ])
#         processed_img = V(centre_crop(img).unsqueeze(0))
        
#         # Register hook in the forward pass that copies the feature vector out
#         # of the Neural Net.
#         def copy_hook(m, i, o):
#             feature_vector.copy_(o.data)
#         h = feature_layer.register_forward_hook(copy_hook)

#         # Apply forward pass
#         fp = self.model.forward(processed_img) 
        
#         h.remove()
#         return feature_vector.numpy()[0, :, 0, 0]

class CustomResNet():
    def __init__(self):
        self.pretrained_model = VGG16(weights='imagenet', include_top=True)
        self.model = Model(inputs=self.pretrained_model.input, outputs=self.pretrained_model.get_layer("fc2").output)
    
    def get_feature_vector(self, img_path):
        # Reference

        img, x = self.load_image(img_path);
        feat = self.model.predict(x)[0]

        return feat


    def cosine_match(self,img,df):
        img_array = self.preprocess_convert(img)
        vectors = self.model.predict(img_array)[0]

        distances = []
        similar_idx_cosine = [ distance.cosine(vectors, feat) for feat in df["fvector"]]
        idx_closest = sorted(range(len(similar_idx_cosine)), key=lambda k: similar_idx_cosine[k])[0:6]

        # for i in idx_closest:
        #     print(i)
        for i in idx_closest:
            distances.append((i,similar_idx_cosine[i]))

        return distances

    def load_image(self, path):
        #img = image.load_img(path, target_size=self.model.input_shape[1:3])

        img = tf.keras.utils.load_img(path, target_size=self.model.input_shape[1:3])
        x = tf.keras.utils.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        return img, x

    def preprocess_convert(self, img):
        #res = tf.keras.preprocessing.image.smart_resize(img, self.model.input_shape[1:3])
        
        res = tf.image.resize(img, self.model.input_shape[1:3])
        x = tf.keras.utils.img_to_array(res)
        x = np.expand_dims(x, axis=0)
        #x = preprocess_input(x)
        return x        

class PaintingMatcher():
    def __init__(self, path=None, directory=None, features=300, include_fvector=False):
        self.directory = directory
        self.include_fvector = include_fvector

        if path is not None:
            self.load_keypoints(path)
            self.orb = cv2.ORB_create(nfeatures=features)
            self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        else:
            raise ValueError('Path is None.')

        self.neuralnet = CustomResNet()    
    
    @staticmethod
    def generate_keypoints(directory_images, csv_path, features=300, fvector_state = True):
        
        neuralnet = None
        if fvector_state:
            neuralnet = CustomResNet()
        result = []

        directory_list = os.listdir(directory_images)
        detector = cv2.ORB_create(nfeatures=features)

        progress = 0
        printProgressBar(progress, len(directory_list), prefix = 'Progress:', suffix = 'Complete', length = 50)

        for file in directory_list:
            filename = os.fsdecode(file)

            img_path = os.path.join(os.fsdecode(directory_images), filename)
            img = cv2.imread(img_path)
            img = resize_with_aspectratio(img, width=800)
            img_keypoints, img_descriptors = detector.detectAndCompute(img,None)

            keypoints = []
            descriptors = []

            for i in range(len(img_keypoints)):
                point = img_keypoints[i]
                descriptor  = img_descriptors[i]
                temp_keypoint = (point.pt, point.size, point.angle, point.response, point.octave, 
                    point.class_id) 

                keypoints.append(temp_keypoint)
                descriptors.append(descriptor)

            keypoints = np.array(keypoints, dtype=object).tolist()
            descriptors = np.array(descriptors, dtype=object).tolist()

            parts = filename.split("__")
            photo = parts[1][4:]
            painting_number = int(parts[2][:2])
            
            if fvector_state:
                result.append({
                    'id':filename,
                    'keypoints': json.dumps(keypoints),
                    'descriptors': json.dumps(descriptors),
                    'room':  parts[0],
                    'photo': photo,
                    'painting_number': painting_number,
                    'fvector': json.dumps(neuralnet.get_feature_vector(img_path).tolist())
                })
            else:
                result.append({
                    'id':filename,
                    'keypoints': json.dumps(keypoints),
                    'descriptors': json.dumps(descriptors),
                    'room':  parts[0],
                    'photo': photo,
                    'painting_number': painting_number,
                    'fvector': json.dumps([])
                })         

            # Update Progress Bar
            progress += 1
            printProgressBar(progress, len(directory_list), prefix = 'Progress:', suffix = 'Complete', length = 50)

        df = pd.DataFrame(result)
        df.to_csv(csv_path)  

    @staticmethod
    def convert_descriptors(descriptors):
        descriptors = np.array(pd.read_json(descriptors), dtype=np.uint8)
        return descriptors

    @staticmethod
    def convert_fvector(fvectors):
        descriptors = np.array(pd.read_json(fvectors), dtype=np.float32)
        return descriptors

    @staticmethod
    def convert_keypoints(keypoint_array):
        keypoints_result = []
        keypoint_array  =  np.array(pd.read_json(keypoint_array), dtype=object)
        for  p in keypoint_array:
            temp = cv2.KeyPoint(
                x=p[0][0],
                y=p[0][1],
                size=p[1],
                angle=p[2],
                response=p[3],
                octave=p[4],
                class_id=p[5],
            )

            keypoints_result.append(temp)
        return keypoints_result
    
    def load_keypoints(self, data_path):
        # if not path.exist(data_path):
        #     raise ValueError('Invalid path.')

        self.df = pd.read_csv(data_path, ",")
        self.df['descriptors'] = self.df['descriptors'].apply(lambda x: PaintingMatcher.convert_descriptors(x))
        self.df['keypoints'] = self.df['keypoints'].apply(lambda x: PaintingMatcher.convert_keypoints(x))
        
        if self.include_fvector:
            self.df['fvector'] = self.df['fvector'].apply(lambda x: PaintingMatcher.convert_fvector(x))

    def match(self,img_t, display=False, mode=0):
        if(mode == 2):
            img_t = resize_with_aspectratio(img_t, width=800)
            kp_t, des_t = self.orb.detectAndCompute(img_t,  None)


            current_fvec = self.neuralnet.cosine_match(img_t, self.df)

            lowest_distance = 10000000000.0

            if not type(des_t) == np.ndarray:
                return []
            
            # Contains indices and cos similarity
            """
            cos_fvec = [(i, np.dot(current_fvec, fvec)/(np.linalg.norm(current_fvec)*np.linalg.norm(fvec))) for i, fvec in enumerate(self.df['fvector'])]
            cos_fvec = sorted(cos_fvec, key= lambda x: x[1])
            best_fvec_indices = [i[0] for i in cos_fvec]

            [cv2.imshow('orbbe' + str(i), resize_with_aspectratio(cv2.imread(os.path.join(self.directory, self.get_filename(best_fvec_indices[i]))), width=400)) for i in range(10)]
            cv2.waitKey(0)
            # Slice dataframe so it only contains images deemed good by the neuralnet
            """

            distances = []
            # TODO: niet matchen tegen de volledige db maar tegen een subset
            #for i, desc in enumerate(self.df.iloc[best_fvec_indices]['descriptors']):
            for i, desc in enumerate(self.df['descriptors']):
                matches = self.bf.match(desc, des_t)
                matches = sorted(matches, key = lambda x:x.distance)

                sum = 0
                if(len(matches) >= 20):
                    out = []
                    for m in matches[:20]:
                        out.append(m.distance)
            
                    for m in matches[:20]:
                        sum += m.distance

                    distances.append((i,sum))
                    if sum < lowest_distance:
                        lowest_distance = sum

            distances = sorted(distances,key=lambda t: t[1])


            if(display):
                # for i in range(1):
                #     if(len(distances) > i):
                #         img_path = os.path.join(self.directory, self.df.id[distances[i][0]])
                #         img = resize_with_aspectratio(cv2.imread(img_path, flags = cv2.IMREAD_COLOR), width=800)
                #         matches = self.bf.match(self.df.descriptors[distances[i][0]], des_t)
                #         matches = sorted(matches, key = lambda x:x.distance)
                #         result = cv2.drawMatches(img, self.df.keypoints[distances[i][0]], img_t, kp_t, matches[:20], None)

                #         #cv2.imshow("Query", img_t)
                #         cv2.namedWindow("Result " + str(i + 1), flags=cv2.WINDOW_NORMAL)
                #         cv2.imshow("Result " + str(i + 1), result)



                cv2.namedWindow("Query", flags=cv2.WINDOW_NORMAL)
                cv2.imshow("Query", img_t)

                for i in range(3):
                    if(len(current_fvec) > i):
                        img_path = os.path.join(self.directory, self.df.iloc[current_fvec[i]].id)
                        img = cv2.imread(img_path, flags = cv2.IMREAD_COLOR)
                        img = resize_with_aspectratio(img, width=800)
                        cv2.namedWindow("Resnet " + str(i + 1), flags=cv2.WINDOW_NORMAL)
                        cv2.imshow("Resnet " + str(i + 1), img)
                    
                cv2.waitKey(1)

            return distances
        elif(mode == 0):
            img_t = resize_with_aspectratio(img_t, width=800)
            kp_t, des_t = self.orb.detectAndCompute(img_t,  None)


            lowest_distance = 10000000000.0

            if not type(des_t) == np.ndarray:
                return []
            

            distances = []
            # TODO: niet matchen tegen de volledige db maar tegen een subset
            #for i, desc in enumerate(self.df.iloc[best_fvec_indices]['descriptors']):
            for i, desc in enumerate(self.df['descriptors']):
                matches = self.bf.match(desc, des_t)
                matches = sorted(matches, key = lambda x:x.distance)

                sum = 0
                if(len(matches) >= 20):
                    out = []
                    for m in matches[:20]:
                        out.append(m.distance)
            
                    for m in matches[:20]:
                        sum += m.distance

                    distances.append((i,sum))
                    if sum < lowest_distance:
                        lowest_distance = sum

            distances = sorted(distances,key=lambda t: t[1])


            if(display):
                for i in range(1):
                    if(len(distances) > i):
                        img_path = os.path.join(self.directory, self.df.id[distances[i][0]])
                        img = resize_with_aspectratio(cv2.imread(img_path, flags = cv2.IMREAD_COLOR), width=800)
                        matches = self.bf.match(self.df.descriptors[distances[i][0]], des_t)
                        matches = sorted(matches, key = lambda x:x.distance)
                        result = cv2.drawMatches(img, self.df.keypoints[distances[i][0]], img_t, kp_t, matches[:20], None)

                        #cv2.imshow("Query", img_t)
                        txt = str(distances[i][1])
                        cv2.putText(img=result, text=txt, org=(100, 100), fontFace=cv2.FONT_HERSHEY_PLAIN, fontScale=8, color=(0, 255, 0), thickness=4)
                        cv2.namedWindow("Result " + str(i + 1), flags=cv2.WINDOW_NORMAL)
                        cv2.imshow("Result " + str(i + 1), result)
                    
                cv2.waitKey(1)

            return distances

        elif(mode == 1):
            #img_t = resize_with_aspectratio(img_t, width=224, height=224)
            current_fvec = []
            current_fvec = self.neuralnet.cosine_match(img_t, self.df)
            if(display):
                cv2.namedWindow("Query", flags=cv2.WINDOW_NORMAL)
                cv2.imshow("Query", img_t)

                for i in range(3):
                    if(len(current_fvec) > i):
                        img_path = os.path.join(self.directory, self.df.iloc[current_fvec[i][0]].id)
                        img = cv2.imread(img_path, flags = cv2.IMREAD_COLOR)
                        img = resize_with_aspectratio(img, width=800)
                        cv2.namedWindow("Resnet " + str(i + 1), flags=cv2.WINDOW_NORMAL)
                        cv2.imshow("Resnet " + str(i + 1), img)
                    
                cv2.waitKey(1)

            return current_fvec
        
        return []


    def get_filename(self,index):
        return self.df.id[index]

    def get_room(self,index):
        return self.df.room[index]

    def get_photo(self,index):
        return self.df.photo[index]

    def get_painting_number(self,index):
        return self.df.painting_number[index]

if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise ValueError('Only provide a path to a video')

    path_img = sys.argv[1]
    directory = sys.argv[2]
    path = sys.argv[3]

    """
    img = cv2.imread(path_img)
    detector = PaintingDetector(img)
    contour_results, original_copy = detector.contours(display=True)
    matcher  = PaintingMatcher("/Users/lennertsteyaert/Documents/GitHub/computervisie-group8/src/data/keypoints.csv","/Users/lennertsteyaert/Documents/GitHub/computervisie-group8/data/Database")
    for i in  range(len(contour_results)):
        affine_image,crop_img = rectify_contour(contour_results[i],img,display=False)
        soft_matches = matcher.match(crop_img,display=False)

        best_match = soft_matches[0]

        room = matcher.get_room(best_match[0])
        photo = matcher.get_photo(best_match[0])
        painting_number = matcher.get_painting_number(best_match[0])
        
        print(f"Room: {room} photo: {photo} number: {painting_number}")
    """

    # DO NOT RUN AGAIN
    # Sample to create keypoint file
    directory_images = os.fsencode(sys.argv[2])   # data/Database
    csv_path = sys.argv[3] # 'src/data/keypoints_2.csv'
    matcher = PaintingMatcher.generate_keypoints(directory_images,csv_path,100)