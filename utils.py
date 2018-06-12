### Utility class for functions related to data and training
import glob

import keras
from keras import backend as K
from keras.callbacks import TensorBoard
from keras.preprocessing.image import img_to_array, load_img

import numpy as np

import os
from os.path import isfile, isdir

import requests

from skimage.color import rgb2lab, lab2rgb, rgb2gray, gray2rgb
from skimage.transform import resize
from skimage.io import imsave, imread

import tensorflow as tf
from tensorflow import data as tfdata

from tqdm import tqdm
from urllib.request import urlretrieve

import warnings
import zipfile

def configure_tensorflow():
    # Check TensorFlow Version
    print('TensorFlow Version: {}'.format(tf.__version__))

    # Check for a GPU
    if not tf.test.gpu_device_name():
        warnings.warn('No GPU found. Please use a GPU to train your neural network.')
    else:
        print('Default GPU Device: {}'.format(tf.test.gpu_device_name()))

    # Don't pre-allocate memory; allocate as-needed
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True

    # Create a session with the above options specified.
    K.tensorflow_backend.set_session(tf.Session(config=config))


###########################
# Data related functions #
##########################

def save_data_tfrecord(tfrecord_path, dataset_url, google_drive_file_id=None):
    if not os.path.exists('data/'):
        os.makedirs('data/')
    if google_drive_file_id:
        _download_file_from_google_drive(google_drive_file_id, tfrecord_path)
    else:
        image_path = _download_and_save_zip(dataset_url)
        _generate_records(image_path, tfrecord_path, 100)

def _download_file_from_google_drive(id, destination):
    def get_confirm_token(response):
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                return value
        return None

    def save_response_content(response, destination):
        CHUNK_SIZE = 32768
        with open(destination, "wb") as f:
            for chunk in response.iter_content(CHUNK_SIZE):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)

    URL = "https://docs.google.com/uc?export=download"
    session = requests.Session()
    response = session.get(URL, params = { 'id' : id }, stream = True)
    token = get_confirm_token(response)

    if token:
        params = { 'id' : id, 'confirm' : token }
        response = session.get(URL, params = params, stream = True)

    save_response_content(response, destination)

class DownloadProgress(tqdm):
    last_block = 0

    def hook(self, block_num=1, block_size=1, total_size=None):
        self.total = total_size
        self.update((block_num - self.last_block) * block_size)
        self.last_block = block_num

def _download_and_save_zip(url):
    if not os.path.exists('dataset/'):
        os.makedirs('dataset/')
    zip_path = 'dataset/' + url[url.rfind("/") + 1:]
    path = zip_path[:-4]
    if not isdir(path): # True: # 
        with DownloadProgress(unit='B', unit_scale=True, miniters=1, desc=path) as pbar:
            urlretrieve(url, zip_path, pbar.hook)
        print("Extracting content from Zip file")
        zip_ref = zipfile.ZipFile(zip_path, 'r')
        zip_ref.extractall('dataset/')
        zip_ref.close() 
        print("Extraction Complete")
    if os.path.exists(zip_path):
        os.remove(zip_path) # Remove zip file
    return path

def _generate_records(images_path, tf_record_name, batch_size=100):
    '''
    Creates a TF Record containing the pre-processed image consisting of
    1)  L channel input
    2)  ab channels output
    3)  features extracted from MobileNet
    This step is crucial for speed during training, as the major bottleneck
    is the extraction of feature maps from MobileNet. It is slow, and inefficient.
    '''
    if os.path.exists(tf_record_name):
        print("****  Delete old TF Records first! ****")
        exit(0)

    files = glob.glob(images_path + "/*.jpg")
    files = sorted(files)
    nb_files = len(files)

    # Use ZLIB compression to save space and create a TFRecordWriter
    options = tf.python_io.TFRecordOptions(tf.python_io.TFRecordCompressionType.ZLIB)
    writer = tf.python_io.TFRecordWriter(tf_record_name, options)

    size = max(EMBEDDING_IMAGE_SIZE, IMAGE_SIZE)  # keep larger size until stored in TF Record

    X_buffer = []
    for i, fn in enumerate(files):
        try:  # prevent crash due to corrupted imaged
            X = imread(fn)
            X = resize(X, (size, size, 3), mode='constant') # resize to the larger size for now
        except:
            continue

        X_buffer.append(X)

        if len(X_buffer) >= batch_size:
            X_buffer = np.array(X_buffer)
            _serialize_batch(X_buffer, writer, batch_size)  # serialize the image into the TF Record

            del X_buffer  # delete buffered images from memory
            X_buffer = []  # reset to new list

            print("Processed %d / %d images" % (i + 1, nb_files))

    if len(X_buffer) != 0:
        X_buffer = np.array(X_buffer)
        _serialize_batch(X_buffer, writer)  # serialize the remaining images in buffer

        del X_buffer  # delete buffer

    print("Processed %d / %d images" % (nb_files, nb_files))
    print("Finished creating TF Record")

    writer.close()

def _serialize_batch(X, writer, batch_size=100):
    '''
    Processes a batch of images, and then serializes into the TFRecord
    Args:
        X: original image with no preprocessing
        writer: TFRecordWriter
        batch_size: batch size
    '''
    [X_batch, features], Y_batch = _process_batch(X, batch_size)  # preprocess batch

    for j, (img_l, embed, y) in enumerate(zip(X_batch, features, Y_batch)):
        # resize the images to their smaller size to reduce space wastage in the record
        img_l = resize(img_l, (IMAGE_SIZE, IMAGE_SIZE, 1), mode='constant')
        y = resize(y, (IMAGE_SIZE, IMAGE_SIZE, 2), mode='constant')

        example_dict = {
            'image_l': _float32_feature_list(img_l.flatten()),
            'image_ab': _float32_feature_list(y.flatten()),
            'image_features': _float32_feature_list(embed.flatten())
        }
        example_feature = tf.train.Features(feature=example_dict)
        example = tf.train.Example(features=example_feature)
        writer.write(example.SerializeToString())

def _process_batch(X, batchsize=100):
    '''
    Process a batch of images for training
    Args:
        X: a RGB image
    '''
    grayscaled_rgb = gray2rgb(rgb2gray(X))  # convert to 3 channeled grayscale image
    lab_batch = rgb2lab(X)  # convert to LAB colorspace
    X_batch = lab_batch[:, :, :, 0]  # extract L from LAB
    X_batch = X_batch.reshape(X_batch.shape + (1,))  # reshape into (batch, IMAGE_SIZE, IMAGE_SIZE, 1)
    X_batch = 2 * X_batch / 100 - 1.  # normalize the batch
    Y_batch = lab_batch[:, :, :, 1:] / 127  # extract AB from LAB
    features = _extract_features(grayscaled_rgb, batchsize)  # extract features from the grayscale image

    return ([X_batch, features], Y_batch)

feature_extraction_model = None
mobilenet_activations = None

def _extract_features(grayscaled_rgb, batchsize=100):
    # Load up MobileNet only when necessary, not during training
    if feature_extraction_model is None:
        _load_mobilenet()

    grayscaled_rgb_resized = []

    for i in grayscaled_rgb:
        # Resize to size of MobileNet Input
        i = resize(i, (EMBEDDING_IMAGE_SIZE, EMBEDDING_IMAGE_SIZE, 3), mode='constant')
        grayscaled_rgb_resized.append(i)

    grayscaled_rgb_resized = np.array(grayscaled_rgb_resized) * 255.  # scale to 0-255 range for MobileNet preprocess_input
    grayscaled_rgb_resized = preprocess_input(grayscaled_rgb_resized)

    with feature_extraction_model.graph.as_default():  # using the shared graph of Colorization model and MobileNet
        features = _get_pre_activations(grayscaled_rgb_resized, batchsize)  # batchwise get the feature maps
        features = features.reshape((-1, 1000))

    return features

def _load_mobilenet():
    global feature_extraction_model, mobilenet_activations

    # Feature extraction module
    feature_extraction_model = MobileNet(input_shape=(EMBEDDING_IMAGE_SIZE, EMBEDDING_IMAGE_SIZE, 3),
                                         alpha=1.0,
                                         depth_multiplier=1,
                                         include_top=True,
                                         weights='imagenet')

    # Set it up so that we can do inference on MobileNet without training it by mistake
    feature_extraction_model.graph = tf.get_default_graph()
    feature_extraction_model.trainable = False

    # Get the pre-softmax activations from MobileNet
    mobilenet_activations = Model(feature_extraction_model.input, feature_extraction_model.layers[-3].output)
    mobilenet_activations.trainable = False

def _get_pre_activations(grayscale_image, batchsize=100):
    # batchwise retrieve feature map from last layer - pre softmax
    activations = mobilenet_activations.predict(grayscale_image, batch_size=batchsize)
    return activations

def _float32_feature_list(floats):
    return tf.train.Feature(float_list=tf.train.FloatList(value=floats))

def _construct_dataset(record_path, batch_size, sess):
    def parse_record(serialized_example):
        # parse a single record
        features = tf.parse_single_example(
            serialized_example,
            features={
                'image_l': tf.FixedLenFeature([IMAGE_SIZE, IMAGE_SIZE, 1], tf.float32),
                'image_ab': tf.FixedLenFeature([IMAGE_SIZE, IMAGE_SIZE, 2], tf.float32),
                'image_features': tf.FixedLenFeature([1000, ], tf.float32)
            })

        l, ab, embed = features['image_l'], features['image_ab'], features['image_features']
        return l, ab, embed

    dataset = tfdata.TFRecordDataset([record_path], 'ZLIB')  # create a Dataset to wrap the TFRecord
    dataset = dataset.map(parse_record, num_parallel_calls=2)  # parse the record
    dataset = dataset.repeat()  # repeat forever
    dataset = dataset.batch(batch_size)  # batch into the required batchsize
    dataset = dataset.shuffle(buffer_size=5)  # shuffle the batches
    iterator = dataset.make_initializable_iterator()  # get an iterator over the dataset

    sess.run(iterator.initializer)  # initialize the iterator
    next_batch = iterator.get_next()  # get the iterator Tensor

    return dataset, next_batch


##############################
# Training related functions #
##############################

def train_generator(batch_size):
    '''
    Generator which wraps a tf.data.Dataset object to read in the
    TFRecord more conveniently.
    '''
    if not os.path.exists(TRAIN_RECORDS_PATH):
        print("\n\n", '*' * 50, "\n")
        print("Please create the TFRecord of this dataset by running `data_utils.py` script")
        exit(0)

    with tf.Session() as train_gen_session:
        dataset, next_batch = _construct_dataset(TRAIN_RECORDS_PATH, batch_size, train_gen_session)

        while True:
            try:
                l, ab, features = train_gen_session.run(next_batch)  # retrieve a batch of records
                yield ([l, features], ab)
            except:
                # if it crashes due to some reason
                iterator = dataset.make_initializable_iterator()
                train_gen_session.run(iterator.initializer)
                next_batch = iterator.get_next()

                l, ab, features = train_gen_session.run(next_batch)
                yield ([l, features], ab)

def val_batch_generator(batch_size):
    '''
    Generator which wraps a tf.data.Dataset object to read in the
    TFRecord more conveniently.
    '''
    if not os.path.exists(VAL_RECORDS_PATH):
        print("\n\n", '*' * 50, "\n")
        print("Please create the TFRecord of this dataset by running `data_utils.py` script with validation data")
        exit(0)

    with tf.Session() as val_generator_session:
        dataset, next_batch = _construct_dataset(VAL_RECORDS_PATH, batch_size, val_generator_session)

        while True:
            try:
                l, ab, features = val_generator_session.run(next_batch)  # retrieve a batch of records
                yield ([l, features], ab)
            except:
                # if it crashes due to some reason
                iterator = dataset.make_initializable_iterator()
                val_generator_session.run(iterator.initializer)
                next_batch = iterator.get_next()

                l, ab, features = val_generator_session.run(next_batch)
                yield ([l, features], ab)

'''
Below is a modification to the TensorBoard callback to perform 
batchwise writing to the tensorboard, instead of only at the end
of the batch.
'''
class TensorBoardBatch(TensorBoard):
    def __init__(self, *args, **kwargs):
        super(TensorBoardBatch, self).__init__(*args)

    def on_batch_end(self, batch, logs=None):
        logs = logs or {}

        for name, value in logs.items():
            if name in ['batch', 'size']:
                continue
            summary = tf.Summary()
            summary_value = summary.value.add()
            summary_value.simple_value = value.item()
            summary_value.tag = name
            self.writer.add_summary(summary, batch)

        self.writer.flush()

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}

        for name, value in logs.items():
            if name in ['batch', 'size']:
                continue
            summary = tf.Summary()
            summary_value = summary.value.add()
            summary_value.simple_value = value.item()
            summary_value.tag = name
            self.writer.add_summary(summary, epoch * self.batch_size)

        self.writer.flush()

#############################
# Testing related functions #
#############################

def load_test_data(dataset_url, image_size, top_index):
    image_folder_path = _download_and_save_zip(dataset_url)
    X = []
    files = os.listdir(image_folder_path)

    files = files[:top_index]
    for i, filename in enumerate(files):
        img = img_to_array(load_img(os.path.join(image_folder_path, filename))) / 255.
        img = resize(img, (image_size, image_size, 3)) * 255.  # resize needs floats to be in 0-1 range, preprocess needs in 0-255 range
        X.append(img)

        if i % (len(files) // 20) == 0:
            print("Loaded %0.2f percentage of images from directory" % (i / float(len(files)) * 100))

    X = np.array(X, dtype='float32')
    print("Images loaded. Shape = ", X.shape)
    return X

def prepare_input_image_batch(X, batchsize=100):
    '''
    This is a helper function which does the same as _preprocess_batch,
    but it is meant to be used with images during testing, not training.
    Args:
        X: A grayscale image
    '''
    X_processed = X / 255.  # normalize grayscale image
    X_grayscale = gray2rgb(rgb2gray(X_processed))
    X_features = _extract_features(X_grayscale, batchsize)
    X_lab = rgb2lab(X_grayscale)[:, :, :, 0]
    X_lab = X_lab.reshape(X_lab.shape + (1,))
    X_lab = 2 * X_lab / 100 - 1.

    return X_lab, X_features


def postprocess_output(X_lab, y, image_size=None):
    '''
    This is a helper function for test time to convert and save the
    the processed image into the 'results' directory.
    Args:
        X_lab: L channel extracted from the grayscale image
        y: AB channels predicted by the colorizer network
        image_size: output image size
    '''
    if not os.path.exists('results/'):
        os.makedirs('results/')
    y *= 127.  # scale the predictions to [-127, 127]
    X_lab = (X_lab + 1) * 50.  # scale the L channel to [0, 100]

    image_size = IMAGE_SIZE if image_size is None else image_size  # set a default image size if needed

    for i in range(len(y)):
        cur = np.zeros((image_size, image_size, 3))
        cur[:, :, 0] = X_lab[i, :, :, 0]
        cur[:, :, 1:] = y[i]
        imsave("results/img_%d.png" % (i + 1), lab2rgb(cur))

        if i % (len(y) // 20) == 0:
            print("Finished processing %0.2f percentage of images" % (i / float(len(y)) * 100))
