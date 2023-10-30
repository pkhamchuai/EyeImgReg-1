import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
import random
import math
from skimage.metrics import structural_similarity as ssim
from utils.SuperPoint import PointTracker
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchir.metrics import NCC
from skimage.metrics import structural_similarity as SSIM
import sys

from utils.utils0 import transform_to_displacement_field


# TODO: put training and testing functions here

class MSE_SSIM:
    def __init__(self):
        self.mse = nn.MSELoss()

    def __call__(self, img1, img2):
        img1 = img1[0, 0, :, :]
        img2 = img2[0, 0, :, :]
        img1_numpy = img1.detach().cpu().numpy()
        img2_numpy = img2.detach().cpu().numpy()
        return self.mse(img1, img2) + \
            (1/SSIM(img1_numpy, img2_numpy, data_range=img2_numpy.max() - img2_numpy.min()))


class MSE_NCC:
    def __init__(self):
        self.mse = nn.MSELoss()
        self.ncc = NCC()

    def __call__(self, img1, img2):
        return self.mse(img1, img2) + (1/self.ncc(img1, img2))


class MSE_SSIM_NCC:
    def __init__(self):
        self.mse = nn.MSELoss()
        self.ncc = NCC()

    def __call__(self, img1, img2):
        img1_numpy = img1.detach().cpu().numpy()
        img2_numpy = img2.detach().cpu().numpy()
        return self.mse(img1, img2) + (1/SSIM(img1_numpy, img2_numpy, data_range=img2_numpy.max() - img2_numpy.min())) + (1/self.ncc(img1, img2))
    

class loss_extra:
    def __init__(self):
        pass

    def __call__(self, affine1):
        # affine1 is a 2D array of shape (2, 3)
        # limit values of the parameters to be within the range of -20 to 20
        # if any parameter is outside the range, return a large value
        # otherwise, return 0
        return torch.sum(torch.abs(affine1) > 20) * 1000


class loss_affine:
    def __init__(self):
        self.mse = nn.MSELoss()

    def __call__(self, affine1, affine2):
        return self.mse(affine1, affine2) #+ loss_extra(affine1)
    

class ModelParams:
    def __init__(self, dataset=0, sup=0, image=1, heatmaps=0, loss_image=0, 
                 learning_rate=0.001, decay_rate = 0.96, num_epochs=10, batch_size=1):
        # dataset: dataset used
        # dataset=0: actual eye
        # dataset=1: synthetic eye
        # dataset=2: synthetic shape
        # sup: supervised or unsupervised model
        # sup=0: unsupervised model
        # sup=1: supervised model
        # image: image type
        # image=0: image not used
        # image=1: image used
        # heatmaps: heatmaps used
        # heatmaps=0: heatmaps not used
        # heatmaps=1: heatmaps used
        # heatmaps=2: enhanced heatmaps used
        # loss_image: loss function for image
        # loss_image=0: MSE
        # loss_image=1: NCC
        # loss_image=2: MSE + SSIM
        # loss_image=3: MSE + NCC
        # loss_image=4: MSE + SSIM + NCC
        # loss_affine is depending on sup
        # loss_affine: loss function for affine
        # loss_affine=0: loss_extra
        # loss_affine=1: loss_affine

        self.dataset = dataset
        self.sup = sup
        self.image = image
        self.heatmaps = heatmaps

        self.learning_rate = learning_rate
        self.decay_rate = decay_rate
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        # print("Learning rate: ", learning_rate)
        # print("Number of epochs: ", num_epochs)
        # print("Batch size: ", batch_size)
        # print("Loss image: ", 'MSE' if self.loss_image == 0 else 
        #                      'NCC' if self.loss_image == 1 else 
        #                      'MSE + SSIM' if self.loss_image == 2 else 
        #                      'MSE + NCC' if self.loss_image == 3 else 
        #                      'MSE + SSIM + NCC')
    
        if loss_image == 0:
            self.loss_image_case = 0
            self.loss_image = nn.MSELoss()
        elif loss_image == 1:
            self.loss_image_case = 1
            self.loss_image = NCC()
        elif loss_image == 2:
            self.loss_image_case = 2
            self.loss_image = MSE_SSIM()
        elif loss_image == 3:
            self.loss_image_case = 3
            self.loss_image = MSE_NCC()
        elif loss_image == 4:
            self.loss_image_case = 4
            self.loss_image = MSE_SSIM_NCC()
        
        if sup == 1:
            self.loss_affine = loss_affine()
        elif sup == 0:
            # self.loss_affine = loss_extra()
            self.loss_affine = None

        self.start_epoch = 0
        self.model_name = self.get_model_name()
        self.model_code = self.get_model_code()
        print('Model name: ', self.model_name)
        print('Model code: ', self.model_code)
        print('Model params: ', self.to_dict())

    def get_model_name(self):
        # model name code
        model_name = 'dataset' + str(self.dataset) + '_sup' + str(self.sup) + '_image' + str(self.image) + \
            '_heatmaps' + str(self.heatmaps) + '_loss_image' + str(self.loss_image_case)
        return model_name
    
    def get_model_code(self):
        # model code
        model_code = str(self.dataset) + str(self.sup) + str(self.image) + \
            str(self.heatmaps) + str(self.loss_image_case) + \
            '_' + str(self.learning_rate) + '_' + str(self.start_epoch) + '_' + \
                str(self.num_epochs) + '_' + str(self.batch_size)
        return model_code

    def to_dict(self):
        return {
            'dataset': self.dataset,
            'sup': self.sup,
            'image': self.image,
            'heatmaps': self.heatmaps,
            'loss_image_case': self.loss_image_case,
            'loss_image': self.loss_image,
            'loss_affine': self.loss_affine,
            'learning_rate': self.learning_rate,
            'decay_rate': self.decay_rate,
            'start_epoch': self.start_epoch, 
            'num_epochs': self.num_epochs,
            'batch_size': self.batch_size,
            'model_name': self.model_name
        }

    # @classmethod
    # def from_model_name(cls, model_name):
    #     sup = int(model_name.split('_')[0][3:]) if model_name.split('_')[0][3:] else 0
    #     dataset = int(model_name.split('_')[1][7:]) if model_name.split('_')[1][7:] else 0
    #     image = int(model_name.split('_')[2][5:]) if model_name.split('_')[2][5:] else 0
    #     heatmaps = int(model_name.split('_')[3][8:]) if model_name.split('_')[3][8:] else 0
    #     loss_image_case = int(model_name.split('_')[4][10:]) if model_name.split('_')[4][10:] else 0
    #     return cls(sup, dataset, image, heatmaps, loss_image_case)

    @classmethod
    def model_code_from_model_path(cls, model_code):
        # print(model_code.split('/')[-1].split('_')[0:-1])
        split_string = model_code.split('/')[-1].split('_')[0:-1]
        dataset = int(split_string[0][0])
        sup = int(split_string[0][1])
        image = int(split_string[0][2])
        heatmaps = int(split_string[0][3])
        loss_image_case = int(split_string[0][4])
        learning_rate = float(split_string[1])
        if len(split_string) == 5:
            start_epoch = int(split_string[2])
            num_epochs = int(split_string[3])
            batch_size = int(split_string[4])
        else:
            start_epoch = 0
            num_epochs = int(split_string[2])
            batch_size = int(split_string[3])
        # decay_rate = 0.96
        return cls(dataset, sup, image, heatmaps, loss_image_case, learning_rate, start_epoch, num_epochs, batch_size)
    
    @classmethod
    def from_dict(cls, model_dict):
        return cls(model_dict['dataset'], model_dict['sup'], model_dict['image'], \
                   model_dict['heatmaps'], model_dict['loss_image'])
    
    def __str__(self):
        return self.model_name
    
    def print_explanation(self):
        print('\nModel name: ', self.model_name)
        print('Model code: ', self.model_code)
        print('Dataset used: ', 'Actual eye' if self.dataset == 0 else \
                'Synthetic eye' if self.dataset == 1 else \
                'Synthetic shape')
        print('Supervised or unsupervised model: ', 'Supervised' if self.sup else 'Unsupervised')
        print('Image type: ', 'Image not used' if self.image == 0 else \
                'Image used')
        print('Heatmaps used: ', 'Heatmaps not used' if self.heatmaps == 0 else \
                'Heatmaps used' if self.heatmaps == 1 else \
                'Enhanced heatmaps used')
        print('Loss function case: ', self.loss_image_case)
        print('Loss function for image: ', self.loss_image)
        print('Loss function for affine: ', self.loss_affine)
        print('Learning rate: ', self.learning_rate)
        print('Decay rate: ', self.decay_rate)
        print('Start epoch: ', self.start_epoch)
        print('Number of epochs: ', self.num_epochs)
        print('Batch size: ', self.batch_size)
        # print('Model params: ', self.to_dict())
        print('\n')

    def __repr__(self):
        return self.model_name
    

def print_summary(model_params, loss_list, timestamp):
    print("Training output:")
    for i in range(len(loss_list)):
        print(loss_list[i])

    # save the output of print_explanation() and loss_list to a txt file
    output_dir = f"output/{model_params.get_model_code()}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    save_txt_name = f"{output_dir}/train_output_{model_params.get_model_code()}_{timestamp}.txt"

    with open(save_txt_name, 'w') as f:
        f.write(model_params.get_model_code())
        f.write('\n')

    sys.stdout = open(save_txt_name, 'a')
    model_params.print_explanation()
    sys.stdout = sys.__stdout__

    with open(save_txt_name, 'a') as f:
        for i in range(len(loss_list)):
            f.write(str(loss_list[i]) + '\n')
        
    print(f"Output saved to {save_txt_name}")


# Function to overlay points on the image
def overlay_points(image, points, color=(0, 255, 0), radius=5):
    # check and convert image to 3-channel, if grayscale, 
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    # if image is normalized, convert it to 0-255
    if image.max() <= 2:
        image = ((image - image.min()) / (image.max() - image.min()) * 255).astype(np.uint8)
    
    try:
        for point in points.T:
            x, y = int(point[0]), int(point[1])
            cv2.circle(image, (x, y), radius, color, -1)
        # image = ((image - image.min()) / (image.max() - image.min()) * 255).astype(np.uint8)
    except:
        pass
    return image

# Predefined bright colors
bright_colors = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
    (255, 255, 0),  # Yellow
    (0, 255, 255),  # Cyan
    (255, 0, 255),  # Magenta
    (255, 128, 0),  # Orange
    (0, 255, 128),  # Spring Green
    (128, 0, 255),  # Purple
    (255, 0, 128),  # Rose
]

# Function to draw lines connecting points from image 1 to image 2 with random bright colors
def draw_lines(image1, image2, points1, points2, match=None, line_thickness=1, opacity=0.5):
    # Convert grayscale images to 3-channel with repeated intensity value
    if len(image1.shape) == 2:
        image1 = cv2.cvtColor(image1, cv2.COLOR_GRAY2BGR)
    if len(image2.shape) == 2:
        image2 = cv2.cvtColor(image2, cv2.COLOR_GRAY2BGR)

    combined_image = np.concatenate((image1, image2), axis=1)

    if match is None:
        for pt1, pt2 in zip(points1.T, points2.T):
            x1, y1 = int(pt1[0]), int(pt1[1])
            x2, y2 = int(pt2[0] + image1.shape[1]), int(pt2[1])

            # Randomly choose a color from the predefined bright colors
            line_color = random.choice(bright_colors)

            # Draw the line with the chosen color and specified thickness
            cv2.line(combined_image, (x1, y1), (x2, y2), line_color, line_thickness)

            # Add lines with the chosen color and opacity on top of the combined image
            overlay = combined_image.copy()
            cv2.line(overlay, (x1, y1), (x2, y2), line_color, line_thickness)
            cv2.addWeighted(overlay, opacity, combined_image, 1 - opacity, 0, combined_image)

    else:
        for pt1, pt2, value in zip(points1.T, points2.T, match):
            x1, y1 = int(pt1[0]), int(pt1[1])
            x2, y2 = int(pt2[0] + image1.shape[1]), int(pt2[1])

            # Randomly choose a color from the predefined bright colors
            line_color = random.choice(bright_colors)

            # Draw the line with the chosen color and specified thickness
            cv2.line(combined_image, (x1, y1), (x2, y2), line_color, line_thickness)

            # Add lines with the chosen color and opacity on top of the combined image
            overlay = combined_image.copy()
            cv2.line(overlay, (x1, y1), (x2, y2), line_color, line_thickness)
            cv2.addWeighted(overlay, opacity, combined_image, 1 - opacity, 0, combined_image)

            # Add value from 'match' array as text around the beginning of the line on the left image
            value_text = f"{value:.2f}"
            text_x = x1 - 50 if x1 > 50 else x1 + 10
            text_y = y1 + 15
            cv2.putText(combined_image, value_text, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, line_color, 1)

    return combined_image

# function to draw lines connecting original points and the transformed points with random bright colors on one image
def draw_lines_one_image(image, points1, points2, line_thickness=1, opacity=0.5, line_color=None):
    # Convert grayscale images to 3-channel with repeated intensity value
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    for pt1, pt2 in zip(points1.T, points2.T):
        x1, y1 = int(pt1[0]), int(pt1[1])
        x2, y2 = int(pt2[0]), int(pt2[1])

        # If not specified, randomly choose a color from the predefined bright colors
        if line_color is None:
            line_color = random.choice(bright_colors)

        # Draw the line with the chosen color and specified thickness
        cv2.line(image, (x1, y1), (x2, y2), line_color, line_thickness)

        # Add lines with the chosen color and opacity on top of the combined image
        overlay = image.copy()
        cv2.line(overlay, (x1, y1), (x2, y2), line_color, line_thickness)
        cv2.addWeighted(overlay, opacity, image, 1 - opacity, 0, image)

        # show the distance between the two points (MSE)
        '''value = np.mean((pt1 - pt2)**2)
        value_text = f"{value:.2f}"
        text_x = x1 - 50 if x1 > 50 else x1 + 10
        text_y = y1 + 15
        cv2.putText(image, value_text, (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, line_color, 1)'''
        
    return image

# Function to create a heatmap from keypoints
def create_heatmap(image, keypoints, size=5, sigma=1):
    heatmap = np.zeros_like(image)
    for kp in keypoints.T:
        x, y = int(kp[0]), int(kp[1])
        heatmap[y - size:y + size + 1, x - size:x + size + 1] = 1
    heatmap = cv2.GaussianBlur(heatmap, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return heatmap

# Function to create a checkerboard image of image1 and image2 with 10x10 squares
def create_checkerboard(image1, image2):
    checkerboard = np.zeros_like(image1)
    # Create the checkerboard pattern
    width = checkerboard.shape[1]

    tile_size = width / 10
    for i in range(checkerboard.shape[0]):
        for j in range(checkerboard.shape[1]):
            num = (math.floor(i / tile_size) + math.floor(j / tile_size)) % 2
            if num == 0:
                checkerboard[i, j] = image1[i, j]
            else:
                checkerboard[i, j] = image2[i, j]

    return checkerboard

def check_location(points):
    # check if the location of the points in array is within the image
    # return the number of points that are outside the image
    # points is a 2D array of shape (2, N)
    # where N is the number of points
    # the first row is the x coordinate
    # the second row is the y coordinate
    # the image size is 512 x 512
    # the points are assumed to be in the range of 0 to 511
    # return the number of points that are outside the image
    number_outside = np.sum((points < 0) | (points > 511))
    
    # print if there are points outside the image
    if number_outside > 0:
        print(f'Number of points outside the image: {number_outside}')
    # return number_outside

def load_images_from_folder(folder, img_size=(512, 512)):
    images = []
    for filename in os.listdir(folder):
        img_path = os.path.join(folder, filename)
        grayim = cv2.imread(img_path, 0)
        interp = cv2.INTER_AREA
        grayim = cv2.resize(grayim, (img_size[1], img_size[0]), interpolation=interp)
        image = (grayim.astype('float32') / 255.)
        if image is not None:
            images.append(image)
    return images

def RANSAC_affine_plot(name, dir_name, image1_name, image1, image2, 
                       points1, points2, desc1, desc2, heatmap1, heatmap2, plot=True):
    # input both matches from RANSAC and non-RANSAC to affine_transform
    # because we have to create affine transform matrix from matches_RANSAC
    # and apply it to matches1 and matches2
    # display them on the image with different colors
    print('Affine_plot')

    # Part 1 - RANSAC
    # match the points between the two images
    tracker = PointTracker(5, nn_thresh=0.7)
    matches = tracker.nn_match_two_way(desc1, desc2, nn_thresh=0.7)

    # take the elements from points1 and points2 using the matches as indices
    matches1 = points1[:2, matches[0, :].astype(int)]
    matches2 = points2[:2, matches[1, :].astype(int)]

    # MSE and TRE before transformation
    mse_before = np.mean((matches1 - matches2)**2)
    tre_before = np.mean(np.sqrt(np.sum((matches1 - matches2)**2, axis=0)))
    
    # create affine transform matrix from points1 to points2
    # and apply it to points1
    affine_transform1 = cv2.estimateAffinePartial2D(matches1.T, matches2.T)
    print(f'Affine transform matrix from points1 to points2:\n{affine_transform1[0]}')
    matches1_transformed = cv2.transform(matches1.T[None, :, :], affine_transform1[0])
    matches1_transformed = matches1_transformed[0].T

    mse12 = np.mean((matches1_transformed - matches2)**2)
    tre12 = np.mean(np.sqrt(np.sum((matches1_transformed - matches2)**2, axis=0)))

    # create affine transform matrix from points2 to points1
    # and apply it to points2
    affine_transform2 = cv2.estimateAffinePartial2D(matches2[:2, :].T, matches1[:2, :].T)
    print(f'Affine transform matrix from points2 to points1:\n{affine_transform2[0]}')
    matches2_transformed = cv2.transform(matches2.T[None, :, :], affine_transform2[0])
    matches2_transformed = matches2_transformed[0].T

    mse21 = np.mean((matches2_transformed - matches1)**2)
    tre21 = np.mean(np.sqrt(np.sum((matches2_transformed - matches1)**2, axis=0)))

    # transform image 1 and 2 using the affine transform matrix
    image1_transformed = cv2.warpAffine(image1, affine_transform1[0], (512, 512))
    image2_transformed = cv2.warpAffine(image2, affine_transform2[0], (512, 512))

    # calculate the MSE between image1_transformed and image2
    mse12_image = np.mean((image1_transformed - image2)**2)
    # calculate the MSE between image2_transformed and image1
    mse21_image = np.mean((image2_transformed - image1)**2)

    # calculate SSIM between image1_transformed and image2
    ssim12_image = ssim(image1_transformed, image2)
    # calculate SSIM between image2_transformed and image1
    ssim21_image = ssim(image2_transformed, image1)

    # Part 3 - Plotting
    if plot:
        # Create a subplot with 2 rows and 2 columns
        fig, axes = plt.subplot_mosaic("AAFE;BDCG", figsize=(20, 10))

        overlaid1 = overlay_points(image1.copy(), matches1, radius=2)
        overlaid2 = overlay_points(image2.copy(), matches2, radius=2)
        overlaid1_transformed = overlay_points(image1_transformed.copy(), matches1_transformed, radius=2)
        overlaid2_transformed = overlay_points(image2_transformed.copy(), matches2_transformed, radius=2)
        
        # Row 1: Two images side-by-side with overlaid points and lines
        # show also MSE and SSIM between the two images
        axes["A"].imshow(draw_lines(overlaid1, overlaid2, matches1, matches2, matches[2, :]))
        axes["A"].set_title(f"Pair {image1_name} with matched points. MSE (x100): {100*np.mean((image1 - image2)**2):.4f} SSIM (x10): {10*ssim(image1, image2):.4f}")
        axes["A"].axis('off')

        axes["B"].imshow(overlaid1_transformed, cmap='gray')
        axes["B"].set_title(f"Image A transformed to B")
        axes["B"].axis('off')

        axes["C"].imshow(overlaid2_transformed, cmap='gray')
        axes["C"].set_title(f"Image B transformed to A")
        axes["C"].axis('off')

        # New subplot for histograms of 'match_score' array
        '''axes["D"].hist(match_score, bins=20, color='blue', alpha=0.7)
        axes["D"].set_title(f"Match Score Histogram, {len(match_score)} matches")
        axes["D"].set_xlabel("Value")
        axes["D"].set_ylabel("Frequency")'''

        # New subplot for the transformed points
        # Blue: from original locations from image 2/1 to the affine-transformed locations
        # Red: from affine-transformed locations of points from image 2/1 to 
        # the locations they supposed to be in image 1/2
        img2 = draw_lines_one_image(overlaid2, matches1_transformed, matches1, line_color=(0, 0, 155))
        img2 = draw_lines_one_image(img2, matches2, matches1_transformed, line_color=(255, 0, 0))
        axes["F"].imshow(img2)
        axes["F"].set_title(f"Image B with points A transformed to B. MSE: {mse12:.4f}")
        axes["F"].axis('off')
        
        img1 = draw_lines_one_image(overlaid1, matches2_transformed, matches2, line_color=(0, 0, 155))
        img1 = draw_lines_one_image(img1, matches1, matches2_transformed, line_color=(255, 0, 0))
        axes["E"].imshow(img1)
        axes["E"].set_title(f"Image A with points B transformed to A. MSE: {mse21:.4f}")
        axes["E"].axis('off')        

        # Display the checkerboard image 1 transformed to 2
        checkerboard = create_checkerboard(overlaid1_transformed, overlaid2)
        axes["D"].imshow(checkerboard, cmap='gray')
        axes["D"].set_title(f"Checkerboard A to B: {mse12_image:.4f}")
        axes["D"].axis('off')

        # Display the checkerboard image 2 transformed to 1
        checkerboard = create_checkerboard(overlaid2_transformed, overlaid1)
        axes["G"].imshow(checkerboard, cmap='gray')
        axes["G"].set_title(f"Checkerboard B to A: {mse21_image:.4f}")
        axes["G"].axis('off')
        
        plt.tight_layout()  # Adjust the layout to leave space for the histogram
        # create a folder named as yyyy-mm-dd_hh in output_images folder      
        plt.savefig(os.path.join(dir_name, f"{image1_name}_normal.png"))
        
        # save images to output folder
        '''cv2.imwrite(f"../Dataset/output_images/transformed_images/{image1_name}_{image2_name}_{name}_1.png", image1_transformed*255)
        cv2.imwrite(f"../Dataset/output_images/transformed_images/{image1_name}_{image2_name}_{name}_2.png", image2_transformed*255)'''
        plt.close()


    print('RANSAC_affine_plot')
    matches_RANSAC = tracker.ransac(matches1.T, matches2.T, matches, max_reproj_error=2)
            
    # take elements from matches1 and matches2 where matches_RANSAC is TRUE
    matches_RANSAC = matches_RANSAC.reshape(-1)
    matches1_RANSAC = matches1[:, matches_RANSAC]
    matches2_RANSAC = matches2[:, matches_RANSAC]

    '''# take elements from matches1 and matches2 where matches_RANSAC is FALSE
    matches1_outliers = matches1[:2, ~matches_RANSAC]
    matches2_outliers = matches2[:2, ~matches_RANSAC]
    # print(f'outliers: {matches1_outliers.shape}, {matches2_outliers.shape}')'''

    # Part 2 - Affine Transform
    # create affine transform matrix from points1 to points2 and apply it to points1
    # also from points2 to points1 and apply it to points2
    # points1 and points2 are 2D arrays of shape (2, N)
    # where N is the number of points
    # the first row is the x coordinate
    # the second row is the y coordinate
    # the image size is 512 x 512

    #################################### FIX THIS ####################################
    # create affine transform matrix using only matches_RANSAC
    # and apply it to all points, plot all first, then plot RANSAC over it
    affine_transform1 = cv2.estimateAffinePartial2D(matches1_RANSAC.T, matches2_RANSAC.T)
    print(f'Affine transform matrix from points1 to points2:\n{affine_transform1[0]}')
    matches1_all_transformed = cv2.transform(matches1.T[None, :, :], affine_transform1[0], (512, 512))
    matches1_all_transformed = matches1_all_transformed[0].T

    matches1_inliers_transformed = matches1_all_transformed[:, matches_RANSAC]

    # create affine transform matrix from points2 to points1
    # and apply it to all points, plot all first, then plot RANSAC over it
    affine_transform2 = cv2.estimateAffinePartial2D(matches2_RANSAC.T, matches1_RANSAC.T)
    print(f'Affine transform matrix from points2 to points1:\n{affine_transform2[0]}')
    matches2_all_transformed = cv2.transform(matches2.T[None, :, :], affine_transform2[0], (512, 512))
    matches2_all_transformed = matches2_all_transformed[0].T

    matches2_inliers_transformed = matches2_all_transformed[:, matches_RANSAC]

    #################################### Metrics for points ####################################
        
    # calculate the MSE between points1_transformed and points2
    mse12_RANSAC = np.mean((matches1_all_transformed - matches2)**2)
    tre12_RANSAC = np.mean(np.sqrt(np.sum((matches1_all_transformed - matches2)**2, axis=0)))

    # calculate the MSE between points2_transformed and points1
    mse21_RANSAC = np.mean((matches2_all_transformed - matches1)**2)
    tre21_RANSAC = np.mean(np.sqrt(np.sum((matches2_all_transformed - matches1)**2, axis=0)))

    #################################### Metrics for images ####################################
    # transform image 1 and 2 using the affine transform matrix
    image1_transformed = cv2.warpAffine(image1, affine_transform1[0], (512, 512))
    image2_transformed = cv2.warpAffine(image2, affine_transform2[0], (512, 512))

    # calculate the MSE between image1_transformed and image2
    mse12_image_RANSAC = np.mean((image1_transformed - image2)**2)
    # calculate the MSE between image2_transformed and image1
    mse21_image_RANSAC = np.mean((image2_transformed - image1)**2)

    # calculate SSIM between image1_transformed and image2
    ssim12_image_RANSAC = ssim(image1_transformed, image2)
    # calculate SSIM between image2_transformed and image1
    ssim21_image_RANSAC = ssim(image2_transformed, image1)

    # take the match score of the elements in matches_RANSAC to plot with lines
    match_score = matches[2, matches_RANSAC]

    # Part 3 - Plotting
    if plot:
        # Create a subplot with 2 rows and 2 columns
        fig, axes = plt.subplot_mosaic("AAFE;BDCG", figsize=(20, 10))

        overlaid1 = overlay_points(image1.copy(), matches1, radius=2)
        overlaid2 = overlay_points(image2.copy(), matches2, radius=2)
        overlaid1_transformed = overlay_points(image1_transformed.copy(), matches1_all_transformed, radius=2)
        overlaid2_transformed = overlay_points(image2_transformed.copy(), matches2_all_transformed, radius=2)
        
        # Row 1: Two images side-by-side with overlaid points and lines
        # show also MSE and SSIM between the two images
        axes["A"].imshow(draw_lines(overlaid1, overlaid2, matches1_RANSAC, matches2_RANSAC, match_score))
        axes["A"].set_title(f"(RANSAC) Pair {image1_name} with matched points. MSE (x100): {100*np.mean((image1 - image2)**2):.4f} SSIM (x10): {10*ssim(image1, image2):.4f}")
        axes["A"].axis('off')

        axes["B"].imshow(overlaid1_transformed, cmap='gray')
        axes["B"].set_title(f"Image A transformed to B")
        axes["B"].axis('off')
        
        axes["C"].imshow(overlaid2_transformed, cmap='gray')
        # axes["C"].imshow(image2_transformed, cmap='gray')
        axes["C"].set_title(f"Image B transformed to A")
        axes["C"].axis('off')

        # New subplot for the transformed points
        # Blue: from original locations from image 2/1 to the affine-transformed locations
        # Red: from affine-transformed locations of points from image 2/1 to 
        # the locations they supposed to be in image 1/2 (Non-RANSAC)
        # Green: from affine-transformed locations of points from image 2/1 to 
        # the locations they supposed to be in image 1/2 (Non-RANSAC)

        # image 2 with lines connecting RANSAC inliers and outliers in different colors
        img2 = draw_lines_one_image(overlaid2, matches1_all_transformed, matches1, line_color=(0, 0, 155))
        img2 = draw_lines_one_image(img2, matches2, matches1_all_transformed, line_color=(255, 0, 0))
        img2 = draw_lines_one_image(img2, matches1_inliers_transformed, matches1_RANSAC, line_color=(0, 255, 0))
        # img2 = draw_lines_one_image(img2, matches2_RANSAC, matches1_inliers_transformed, line_color=(0, 255, 0))

        axes["F"].imshow(img2)
        axes["F"].set_title(f"Image B with points A transformed to B. MSE: {mse12_RANSAC:.4f}")
        axes["F"].axis('off')

        img1 = draw_lines_one_image(overlaid1, matches2_all_transformed, matches2, line_color=(0, 0, 155)) # color: blue
        img1 = draw_lines_one_image(img1, matches1, matches2_all_transformed, line_color=(255, 0, 0))
        img1 = draw_lines_one_image(img1, matches2_inliers_transformed, matches2_RANSAC, line_color=(0, 255, 0)) # RANSAC inliers
        # img1 = draw_lines_one_image(img1, matches1_RANSAC, matches2_inliers_transformed, line_color=(0, 255, 0)) # RANSAC inliers
        
        axes["E"].imshow(img1)
        axes["E"].set_title(f"Image A with points B transformed to A. MSE: {mse21_RANSAC:.4f}")
        axes["E"].axis('off')

        # Display the checkerboard image 1 transformed to 2
        # checkerboard = create_checkerboard(image1_transformed, image2)
        checkerboard = create_checkerboard(overlaid1_transformed, overlaid2)
        axes["D"].imshow(checkerboard, cmap='gray')
        axes["D"].set_title(f"Checkerboard A to B: {mse12_image_RANSAC:.4f}")
        axes["D"].axis('off')

        # Display the checkerboard image 2 transformed to 1
        # checkerboard = create_checkerboard(image2_transformed, image1)
        checkerboard = create_checkerboard(overlaid2_transformed, overlaid1)
        axes["G"].imshow(checkerboard, cmap='gray')
        axes["G"].set_title(f"Checkerboard B to A: {mse21_image_RANSAC:.4f}")
        axes["G"].axis('off')
        
        plt.tight_layout()  # Adjust the layout to leave space for the histogram
        plt.savefig(os.path.join(dir_name, f"{image1_name}_RANSAC.png"))
        plt.close()

    return matches1_transformed.shape[-1], mse_before, mse12, mse21, tre_before, tre12, tre21, \
        mse12_image, mse21_image, ssim12_image, ssim21_image, matches1_inliers_transformed.shape[-1], \
        mse12_RANSAC, mse21_RANSAC, tre12_RANSAC, tre21_RANSAC, mse12_image_RANSAC, mse21_image_RANSAC, \
            ssim12_image_RANSAC, ssim21_image_RANSAC


def blend_img(edge, image):
    """
    Overlaying edges (contour) onto an image.
    :param color:
    :param edge: edges of fixed image
    :param image: moving/warped image
    :return: output image
    """

    edge_color = np.array((255, 255, 0)) / 255.  # now 0 = dark, 255 = light
    # if the image is float, convert to uint8
    if image.dtype == np.float32:
        image = np.uint8(image * 255)
    out = np.zeros((image.shape[0], image.shape[1], 3))
    for i in range(image.shape[0]):
        for j in range(image.shape[1]):
            if edge[i, j] > 127:
                out[i, j] = edge_color
            else:
                out[i, j] = np.array((image[i, j], image[i, j], image[i, j])) / 255.

    # convert image to float
    # out = np.float32(out)
    return out

def transform_points_DVF(points, M, image):
    # transform points using displacement field
    # DVF.shape = (2, H, W)
    # points.shape = (2, N)
    displacement_field = torch.zeros(image.shape[-1], image.shape[-1])
    DVF = transform_to_displacement_field(
        displacement_field.view(1, 1, displacement_field.size(0), displacement_field.size(1)), 
        M.clone().view(1, 2, 3))
    if isinstance(DVF, torch.Tensor):
        DVF = DVF.numpy()
    # loop through each point and apply the transformation
    for i in range(points.shape[1]):
        points[:, i] = points[:, i] - DVF[:, int(points[1, i]), int(points[0, i])]
    return points

# def transform_points_DVF(points, affine_params, image_size):
#     # transform points using displacement field
#     # DVF.shape = (2, H, W)
#     # points.shape = (2, N)

#     displacement_field = torch.zeros(image_size, image_size)
#     DVF = transform_to_displacement_field(
#         displacement_field.view(1, 1, displacement_field.size(0), displacement_field.size(1)), 
#         torch.tensor(affine_params).view(1, 2, 3))

#     # loop through each point and apply the transformation
#     for i in range(points.shape[1]):
#         points[:, i] = points[:, i] - DVF[:, int(points[0, i]), int(points[1, i])]

#     return points


def DL_affine_plot(name, dir_name, image1_name, image2_name, image1, image2, image1_transformed,
                       matches1, matches2, matches1_transformed, desc1, desc2, affine_params_true=None, affine_params_predict=None, heatmap1=None, heatmap2=None, plot=True):
    

    # BEGIN: 4j8d9fj3j9fj
    # print("matches1 shape:", matches1.shape)
    # print("matches2 shape:", matches2.shape)
    # print("matches1_transformed shape:", matches1_transformed.shape)
    # print("desc1 shape:", desc1.shape)
    # print("desc2 shape:", desc2.shape)
    # END: 4j8d9fj3j9fj
    # MSE and TRE before transformation
    mse_before = np.mean((matches1 - matches2)**2)
    tre_before = np.mean(np.sqrt(np.sum((matches1 - matches2)**2, axis=0)))
    
    # matches1_transformed = cv2.transform(matches1.T[None, :, :], affine_params[0])
    # matches1_transformed = matches1_transformed[0].T

    mse12 = np.mean((matches1_transformed - matches2)**2)
    tre12 = np.mean(np.sqrt(np.sum((matches1_transformed - matches2)**2, axis=0)))

    # calculate the MSE between image1_transformed and image2
    mse12_image_before = np.mean((image1 - image2)**2)
    mse12_image = np.mean((image1_transformed - image2)**2)

    # calculate SSIM between image1_transformed and image2
    ssim12_image_before = ssim(image1, image2, data_range=image2.max() - image2.min())
    ssim12_image = ssim(image1_transformed, image2, data_range=image2.max() - image2.min())

    # Part 3 - Plotting
    if plot:
        try:
            # Create a subplot with 2 rows and 2 columns
            fig, axes = plt.subplot_mosaic("AADE;BCFG", figsize=(20, 10))

            overlaid1 = overlay_points(image1.copy(), matches1, radius=1)
            overlaid2 = overlay_points(image2.copy(), matches2, radius=1)
            overlaid1to2 = overlay_points(overlaid1.copy(), matches1_transformed, color=(155, 0, 0), radius=1)
            # overlaid1to2 = overlay_points(overlaid1to2.copy(), matches1, color=(0, 0, 155), radius=1)
            # true points in black, transformed points in white
            overlaid12_error = overlay_points(overlaid2.copy(), matches1_transformed, color=(0, 0, 155), radius=1)

            # Row 1: Two images side-by-side with overlaid points and lines
            output_overlaid = overlay_points(image1_transformed.copy(), matches1_transformed, radius=1)
            axes["F"].imshow(output_overlaid, cmap='gray')
            axes["F"].set_title(f"Output, {affine_params_predict[0]}")
            axes["F"].axis('off')
            axes['F'].grid(True)

            # axe B shows source image
            axes["B"].imshow(overlaid1, cmap='gray')
            axes["B"].set_title(f"Source, MSE: {mse12_image_before:.4f} SSIM: {ssim12_image_before:.4f}")
            axes["B"].axis('off')
            axes['B'].grid(True)

            # axe C shows target image
            axes["C"].imshow(overlaid2, cmap='gray')
            if affine_params_true is not None:
                axes["C"].set_title(f"Target, {affine_params_true[0]}")
            else:
                axes["C"].set_title(f"Target (unsupervised)")
            axes["C"].axis('off')
            axes['C'].grid(True)

            # New subplot for the transformed points
            # Blue: from original locations from image 2/1 to the affine-transformed locations
            # Red: from affine-transformed locations of points from image 2/1 to 
            # the locations they supposed to be in image 1/2
            try:
                imgD = draw_lines_one_image(overlaid1to2, matches1_transformed, matches1, line_color=(0, 0, 155))
                axes["D"].imshow(imgD)
            except:
                axes["D"].imshow(overlaid1to2)
            # img2 = draw_lines_one_image(img2, matches2, matches1_transformed, line_color=(255, 0, 0))
            axes["D"].set_title(f"SrcImg, Transformation lines.")
            axes["D"].axis('off')

            # img2 = draw_lines_one_image(overlaid2, matches1_transformed, matches1, line_color=(0, 0, 155))
            try:
                imgE = draw_lines_one_image(overlaid12_error, matches2, matches1_transformed, line_color=(155, 0, 0))
                axes["E"].imshow(imgE)
            except:
                axes["E"].imshow(overlaid12_error)
            axes["E"].set_title(f"TrgImg, Error lines. MSE: {mse12:.4f}, TRE: {tre12:.4f}")
            axes["E"].axis('off')

            # Display the checkerboard image 1 transformed to 2
            checkerboard = create_checkerboard(image1_transformed, image2)
            axes["G"].imshow(checkerboard, cmap='gray')
            axes["G"].set_title(f"Checker, MSE: {mse12_image:.4f}, SSIM: {ssim12_image:.4f}")
            axes["G"].axis('off')

            # show also MSE and SSIM between the two images
            imgA = draw_lines(overlaid1, overlaid2, matches1, matches2, match=None)
            axes["A"].imshow(imgA)
            axes["A"].set_title(f"Pair {image1_name}. MSE: {mse_before:.4f}, TRE: {tre_before:.4f}")
            axes["A"].axis('off')

            # axes G shows edge of image 1 over image 2
            # find the edges of the transformed image
            '''kernel = np.ones((3, 3), np.uint8)
            edges = cv2.Canny((image1_transformed*255).astype(np.uint8), 15, 200)
            # edges = cv2.dilate(edges, kernel, iterations=1)
            edge_overlay = blend_img(edges, image2)
            print("E")
            axes["E"].imshow(edge_overlay)
            axes["E"].set_title(f"Edges of source over target")
            axes["E"].axis('off')'''

            
            plt.tight_layout()  # Adjust the layout to leave space for the histogram
            # if the directory does not exist, create it
            # dir_name = f"../Dataset/output_images/transformed_images/{image1_name}_{image2_name}"
            if not os.path.exists(dir_name):
                os.makedirs(dir_name) 
            plt.savefig(os.path.join(dir_name, f"{name}_{image1_name}.png"))
            
            # save images to output folder
            '''cv2.imwrite(f"../Dataset/output_images/transformed_images/{image1_name}_{image2_name}_{name}_1.png", image1_transformed*255)
            cv2.imwrite(f"../Dataset/output_images/transformed_images/{image1_name}_{image2_name}_{name}_2.png", image2_transformed*255)'''
            plt.close()
            
        except TypeError:
            print("TypeError in plotting")
            pass

    return matches1_transformed, mse_before, mse12, tre_before, tre12, \
        mse12_image_before, mse12_image, ssim12_image_before, ssim12_image

