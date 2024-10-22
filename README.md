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
  - [Table](#table)
  - [Image Visualisation](#Image-Visualisation)
  - [3D Visualisation](#3D-Visualisation)
    
- [Conclusions](#conclusion)

## Introduction:
  Splatter image rendering is a technique used for high-quality image generation by modeling object surfaces with Gaussian splats. This project aims to introduce an enhancement to this method by utilizing a new loss function that compares predicted splatter images to a desired 'target' splatter image, thereby providing better supervision for training deep models. This supervised learning approach improve the quality of the generated images.
## New loss fucntion:
  The new loss function introduced in this project is designed to provide better supervision to the model by comparing the predicted splatter images to a 'target' splatter image generated from multi-view data. This loss function is a combination of multiple components, each designed to measure the differences between the predicted and target images for different channels (e.g., xyz, opacity).
### Target Splatter image:
  we created the target splatter image reconstrucntion by using two views. The idea is to use it as ground truth reconstruction and to comapre it with the generated reconstruction of the model. by using it we aim to enhance the model performance.
### Normalization:
Before calculating the loss, the channels (e.g., xyz, scaling) from the predicted and target images are normalized using min-max normalization. This ensures that the values are within a consistent range between 0 and 1.

### Loss Function:
The custom loss function is defined as: 
L<sub>total</sub> = L<sub>base</sub> &plus;  &lambda; &times; L<sub>new</sub>

&lambda;: we set lambda to 0.01

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
- The target reconstruction are saved on the drive but also you can create them by uncomment the lines in eval.py in the section save target reconstruction and run the file.
- **NOTE: make sure that the dataset folder's name that you want to use during training is cars_train.**
- - **NOTE: To create Splatter image target to use during training, you should change the folder's name that contains the dataset to cars_test and run eval.py**
  
## Training:
- Both models were trained on T4(Google Colab)
- Both models were trained for 8,000 iterations.
- Used batch size is 4.
- cfg.data.input_images = 2.

## Results:
### Table:

Here are the reuslts of trainging the base and our model. As we can see our model outperformed the base model in LPIPS and SSIM metrics. but not in PSNR.
| Metric        | Base Model | Our Model  |
| ------------- | ---------- | ---------- |
| LPIPS_cond  ↓ | 0.17512    | 0.1575     |
| LPIPS_novel ↓ | 0.26108    | 0.2101     |
| SSIM_cond ↑   | 0.90609    | 0.8931     |
| SSIM_novel ↑  | 0.84478    | 0.8455     |
| PSNR_cond  ↑  | 23.9634    | 23.0409    |
| PSNR_novel ↑  | 20.47619   | 20.115     |


### Image Visualisation:

| Example No. | Base Model | Our Model  | Ground Truth (GT) |
| ----------- | ---------- | ---------- | ----------------- |
| 1           | ![Base Model 1](base_model_1_url) | ![Our Model 1](our_model_1_url) | ![GT 1](gt_1_url) |
| 2           | ![Base Model 2](base_model_2_url) | ![Our Model 2](our_model_2_url) | ![GT 2](gt_2_url) |
| 3           | ![Base Model 3](base_model_3_url) | ![Our Model 3](our_model_3_url) | ![GT 3](gt_3_url) |
| 4           | ![Base Model 4](base_model_4_url) | ![Our Model 4](our_model_4_url) | ![GT 4](gt_4_url) |

### 3D Visualisation:
gggg

## Conclusions:
 Incorporating an additional loss during training shows that our model outperforms the base model in perceptual quality, as seen in the LPIPS and SSIM metrics. It generates images closer to the ground truth, with significant improvements in both conditional and novel settings. However, the base model performs better in PSNR, indicating slightly higher pixel-level accuracy.










