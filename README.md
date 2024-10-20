# Splatter Image - Supervise by desired splatter image
In this project we aim to enhance the splatter image rendering by introducing a new loss function that incorporates supervision from a 'target' splatter image The new loss function is designed to improve learning by leveraging multi-view data and comparing reconstructions with the desired target image, thereby guiding the model towards better predictions.
## Table of Contents:
- [Introduction](#Introduction)
- [New Loss Function](#new-loss-function)
  - [Target Splatter Image](#target-splatter-image)
  - [Normalization](#normalization)
  - [Loss Function](#loss-function)

- [Installation](#Installation)
- [Dataset](#Training)
- [Training](#Training)

- [Results](#Results)

## Introduction:
  Splatter image rendering is a technique used for high-quality image generation by modeling object surfaces with Gaussian splats. This project aims to introduce an enhancement to this method by utilizing a new loss function that compares predicted splatter images to a desired 'target' splatter image, thereby providing better supervision for training deep models. This supervised learning approach improve the quality of the generated images.
## New loss fucntion:
  The new loss function introduced in this project is designed to provide better supervision to the model by comparing the predicted splatter images to a 'target' splatter image generated from multi-view data. This loss function is a combination of multiple components, each designed to measure the differences between the predicted and target images for different channels (e.g., xyz, opacity).
### Target Splatter image:
  we created the target splatter image reconstrucntion by using one view only. The idea is to use it as ground truth reconstruction and to comapre it with the generated reconstruction of the model. by using it we aim to enhance the model performance.
### Normalization:
Before calculating the loss, the channels (e.g., xyz, scaling) from the predicted and target images are normalized using min-max normalization. This ensures that the values are within a consistent range.

### Loss Function:
The custom loss function is defined as: 
L<sub>total</sub> = L<sub>base</sub> &plus;  &lambda; &times; L<sub>new</sub>

&lambda;: at the first 3k iteration of the model &lambda; = 0 afterwards &lambda; will be increased.

Which new loss defined as: 
$\Sigma_{c &in; all\O} $
$mean$( O<sub>target</sub>(c<sub>current</sub> &minus; c<sub>target</sub>)<sup>2</sup>)
- Which c represent channel in the current reconstruction of the model.
- O opacity of the current reconstruction
- O<sub>target</sub> represent the target opacity

The idea behind multiplying with target opacity is to **reduce noise in invisible Regions** and to **focus on key features**.
## Installation: 
- follow the instructions on the original repository [Splatter Image Repository](https://github.com/szymanowiczs/splatter-image.git)
## Dataset:
- We used 20% of data from the SRNcars Datasets 
- The target reconstruction are saved on the drive but also you can create them by uncomment the lines in eval.py in the section save target reconstruction and run the file. **NOTE: make sure to change the dataset you want to train on to the name of train_test so in evaluation you can create the target reconstruction based on the training data.**
- the dataset that we trained on is also saved on our drive.
## Training:
- Both models were trained on T4(Google Colab)
- Both models were trained for 15,000 iterations.
- Used batch size is 4. 
- 








