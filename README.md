# Deep Colorization

## Overview

This notebook creates a model that is able to colorize images to a certain extent, which combines a Fast deep Convolutional Neural Network trained from scratch with high-level features extracted from the MobileNet pre-trained model. This encoder-decoder model can process images of any size and aspect ratio. The training of this model is done on 60K images of MS-COCO dataset. How this model performs in coloring images are also showing in result section.

This notebook's work is inspired from https://github.com/titu1994/keras-mobile-colorizer which is also transfer to ipynb notebook too [[link](https://github.com/krypten/MobileDeepColorization/blob/master/deep_colorization_original.ipynb)].

## Introduction

There is something uniquely and powerfully satisfying about the simple act of adding color to black and white imagery. Moreover this coloring of gray-scale images can have a big impact in a wide variety of domains, for instance, re-master of historical images, dormant memories or expressing artistic creativity and improvement of surveillance feeds.

The information content of a gray-scale image is rather limited, thus adding the color components can provide more insights about its semantics. In the context of deep learning, models such as Inception [[ref](https://arxiv.org/pdf/1512.00567.pdf)], VGG [[ref](https://arxiv.org/pdf/1409.1556.pdf)] and others are usually trained using colored image datasets. When applying these networks on grayscale images, a prior colorization step can help improve the results. However, designing and implementing an effective and reliable system that automates this process still remains nowadays as a challenging task.

In this regard, below is the proposed model that is able to colorize images to a certain extent, combining a DCNN architecture which utilizes a U-Net inspired model conditioned on MobileNet class features to generate a mapping from Grayscale to Color image. This work is based on the https://github.com/titu1994/keras-mobile-colorizer and https://github.com/baldassarreFe/deep-koalarization [[research paper](https://arxiv.org/pdf/1712.03400.pdf)].

##### Architecture
![Deep Colorization Architecture](https://raw.githubusercontent.com/krypten/MobileDeepColorization/master/docs/images/deep_colorization_architecture.png)

## Code

The code is built using Keras and Tensorflow. The code in ipnb format and all the explaination is instead it to make it more readable and easy to run.


Source Implementation: https://github.com/titu1994/keras-mobile-colorizer
Source Implementation in python notebook: https://github.com/krypten/MobileDeepColorization/blob/master/deep_colorization_original.ipynb

Improved implementation: https://github.com/krypten/MobileDeepColorization/blob/master/deep_colorization_improved.ipynb