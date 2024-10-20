# Splatter Image - Supervise by desired splatter image
In this project we aim to enhance the splatter image rendering by introducing a new loss function that incorporates supervision from a 'target' splatter image The new loss function is designed to improve learning by leveraging multi-view data and comparing reconstructions with the desired target image, thereby guiding the model towards better predictions.
## Table of Contents:
- [Introduction](#Introduction)
- [New Loss Function](#new-loss-function)
  - [Target Splatter Image](#target-splatter-image)
  - [Normalization](#normalization)
  - [Loss Function](#loss-function)
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
$Total$ $Loss$ = $Base$ $Loss$ &plus;  &lambda; &times; $New$ $Loss$

Which new loss defined as: 
$\Sigma_{channel &in; channels}  x_i$







