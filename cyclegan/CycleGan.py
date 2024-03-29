import os
import time
import numpy as np

import tensorflow as tf
from tensorflow.keras import layers

import matplotlib.pyplot as plt
from IPython.display import clear_output

from resnet.ResNet import ResNet_Blocks

def load_image(image_path, channels=3):
  """Loads and preprocesses images.
  arguments:
    image_path: String. File path or url to read from. If set url, the url must start with "http" or "https.
    channels: Int. Number of channels of images.
  """
  if 'http' in image_path:
    # Get image file from url and cache locally.
    image_path = tf.keras.utils.get_file(os.path.basename(image_path)[-128:], image_path)

  # Load and convert to float32 numpy array, and normalize to range [0, 1].
  image = tf.io.decode_image(tf.io.read_file(image_path), channels=channels, dtype=tf.float32,)
  # Normalize to range [-1, 1]
  image = image*2.0-1.0
  return image

def random_crop_images(dataset, image_size=(64, 64), expand=1.1):
  height, width = image_size
  ex_size = ex_height, ex_width = tuple([int(x*expand) for x in image_size])
  offset_height = np.random.randint(0, ex_height-height)
  offset_width = np.random.randint(0, ex_width-width)

  dataset = dataset.map(lambda x: tf.image.resize(x, ex_size))
  dataset = dataset.map(lambda x: tf.image.crop_to_bounding_box(x, offset_height, offset_width, height, width))
  return dataset

def random_flip_left_right_images(dataset):
  if np.random.randint(2):
    dataset = dataset.map(lambda x: tf.image.flip_left_right(x))
  return dataset

def load_and_preprocessing_data(paths_x, paths_y, image_size=(64, 64), batch_size=5, channels=3, aug_num=5, expand=1.1):
  prep_images=[]
  print('Number of files to load for original:', len(paths_x))
  print('Number of files to load for target:', len(paths_y))

  dataset_x = tf.data.Dataset.from_tensor_slices([])
  dataset_y = tf.data.Dataset.from_tensor_slices([])
  for path_x, path_y in zip(paths_x, paths_y):
    image_x = tf.image.resize(load_image(path_x, channels), image_size)
    image_y = tf.image.resize(load_image(path_y, channels), image_size)
    for _ in range(aug_num):
      dataset_aug = tf.data.Dataset.from_tensor_slices([[image_x, image_y]])
      dataset_aug = random_crop_images(dataset_aug, image_size, expand)
      dataset_aug = random_flip_left_right_images(dataset_aug)
      x, y = next(iter(dataset_aug))
      dataset_x = dataset_x.concatenate(tf.data.Dataset.from_tensor_slices([x]))
      dataset_y = dataset_y.concatenate(tf.data.Dataset.from_tensor_slices([y]))

  print('Total Number of Images:',len(dataset_x))
  buffer_size = len(dataset_x)

  dataset_x = dataset_x.batch(batch_size)
  dataset_y = dataset_y.batch(batch_size)

  print('Batch size:',batch_size)
  print('Num batchs', len(dataset_x))

  return dataset_x, dataset_y

class CycleGanTraining():
  def __init__(self,
               generator_g, # Tf.Model, generator model.
               generator_f, # Tf.Model, generator model.
               discriminator_x, #Tf.Model, discriminator model.
               discriminator_y, #Tf.Model, discriminator model.
               learning_rate = 2e-4, # Learning rate for the discriminator and the generator optimizers
               beta_1 = 0.5,
               beta_2 = 0.999,
               checkpoint_prefix = None,
               ):

    self.generator_g = generator_g
    self.generator_f = generator_f
    self.discriminator_x = discriminator_x
    self.discriminator_y = discriminator_y

    self.LAMBDA = 10
    self.loss_obj = tf.keras.losses.BinaryCrossentropy(from_logits=True)

    # Define the generator optimizers
    # The generator optimizers are different since you will train two networks separately.
    self.generator_g_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1)
    self.generator_f_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1)
    # Define the discriminator optimizers
    # The discriminator optimizers are different since you will train two networks separately.
    self.discriminator_x_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1)
    self.discriminator_y_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1)

    self.checkpoint = tf.train.Checkpoint(
        generator_g = generator_g,
        generator_f = generator_f,
        discriminator_x = discriminator_x,
        discriminator_y = discriminator_y,
        generator_g_optimizer = self.generator_g_optimizer,
        generator_f_optimizer = self.generator_f_optimizer,
        discriminator_x_optimizer = self.discriminator_x_optimizer,
        discriminator_y_optimizer = self.discriminator_y_optimizer,
        )


  def discriminator_loss(self, real, generated):
    real_loss = self.loss_obj(tf.ones_like(real), real)

    generated_loss = self.loss_obj(tf.zeros_like(generated), generated)

    total_disc_loss = real_loss + generated_loss

    return total_disc_loss * 0.5

  def generator_loss(self, generated):
    return self.loss_obj(tf.ones_like(generated), generated)

  def calc_cycle_loss(self, real_image, cycled_image):
    loss1 = tf.reduce_mean(tf.abs(real_image - cycled_image))
    return self.LAMBDA * loss1

  def identity_loss(self, real_image, same_image):
    loss = tf.reduce_mean(tf.abs(real_image - same_image))
    return self.LAMBDA * 0.5 * loss

  def generate_images(self, model, test_input):
    prediction = model(test_input)

    plt.figure(figsize=(12, 12))

    display_list = [test_input[0], prediction[0]]
    title = ['Input Image', 'Predicted Image']

    for i in range(2):
      plt.subplot(1, 2, i+1)
      plt.title(title[i])
      # getting the pixel values between [0, 1] to plot it.
      plt.imshow(display_list[i] * 0.5 + 0.5)
      plt.axis('off')
    plt.show()

  def save(self, checkpoint_prefix=None):
    if checkpoint_prefix:
      return self.checkpoint.save(file_prefix=checkpoint_prefix)
    elif self.checkpoint_prefix:
      return self.checkpoint.save(file_prefix=self.checkpoint_prefix)
    else:
      return None

  def restore(self, save_path):
    return self.checkpoint.restore(save_path)

  @tf.function
  def train_step(self, real_x, real_y):
    # persistent is set to True because the tape is used more than
    # once to calculate the gradients.
    with tf.GradientTape(persistent=True) as tape:
      # Generator G translates X -> Y
      # Generator F translates Y -> X.

      fake_y = self.generator_g(real_x, training=True)
      cycled_x = self.generator_f(fake_y, training=True)

      fake_x = self.generator_f(real_y, training=True)
      cycled_y = self.generator_g(fake_x, training=True)

      # same_x and same_y are used for identity loss.
      same_x = self.generator_f(real_x, training=True)
      same_y = self.generator_g(real_y, training=True)

      disc_real_x = self.discriminator_x(real_x, training=True)
      disc_real_y = self.discriminator_y(real_y, training=True)

      disc_fake_x = self.discriminator_x(fake_x, training=True)
      disc_fake_y = self.discriminator_y(fake_y, training=True)

      # calculate the loss
      gen_g_loss = self.generator_loss(disc_fake_y)
      gen_f_loss = self.generator_loss(disc_fake_x)

      total_cycle_loss = self.calc_cycle_loss(real_x, cycled_x) + self.calc_cycle_loss(real_y, cycled_y)

      # Total generator loss = adversarial loss + cycle loss
      total_gen_g_loss = gen_g_loss + total_cycle_loss + self.identity_loss(real_y, same_y)
      total_gen_f_loss = gen_f_loss + total_cycle_loss + self.identity_loss(real_x, same_x)

      disc_x_loss = self.discriminator_loss(disc_real_x, disc_fake_x)
      disc_y_loss = self.discriminator_loss(disc_real_y, disc_fake_y)

    # Calculate the gradients for generator and discriminator
    generator_g_gradients = tape.gradient(total_gen_g_loss,
                                          self.generator_g.trainable_variables)
    generator_f_gradients = tape.gradient(total_gen_f_loss,
                                          self.generator_f.trainable_variables)

    discriminator_x_gradients = tape.gradient(disc_x_loss,
                                              self.discriminator_x.trainable_variables)
    discriminator_y_gradients = tape.gradient(disc_y_loss,
                                              self.discriminator_y.trainable_variables)

    # Apply the gradients to the optimizer
    self.generator_g_optimizer.apply_gradients(zip(generator_g_gradients,
                                              self.generator_g.trainable_variables))

    self.generator_f_optimizer.apply_gradients(zip(generator_f_gradients,
                                              self.generator_f.trainable_variables))

    self.discriminator_x_optimizer.apply_gradients(zip(discriminator_x_gradients,
                                                  self.discriminator_x.trainable_variables))

    self.discriminator_y_optimizer.apply_gradients(zip(discriminator_y_gradients,
                                                  self.discriminator_y.trainable_variables))

    return disc_x_loss, total_gen_g_loss

  def train(self, train_img, train_tar, epochs):
    gen_loss_list = []
    disc_loss_list = []
    epoch_list = []

    for epoch in range(epochs):
      start = time.time()

      n = 0
      for image_x, image_y in tf.data.Dataset.zip((train_img, train_tar)):
        disc_loss, gen_loss = self.train_step(image_x, image_y)
        print('{}th epoch {}th batch >>> Disc loss: {} , Gen loss: {}'.format(epoch+1, n+1, disc_loss, gen_loss))

        # if n % 10 == 0:
        #   print ('.', end='')
        n += 1

      clear_output(wait=True)
      # Using a consistent image so that the progress of the model
      # is clearly visible.

      sample_img = next(iter(train_img))
      sample_tar = next(iter(train_tar))
      self.generate_images(self.generator_g, sample_img)

      # if (epoch + 1) % 5 == 0:
      #   ckpt_save_path = ckpt_manager.save()
      #   print ('Saving checkpoint for epoch {} at {}'.format(epoch+1,
      #                                                       ckpt_save_path))

      print ('Time taken for epoch {} is {} sec\n'.format(epoch + 1,
                                                          time.time()-start))

      print('Disc loss: {} , Gen loss: {}'.format(disc_loss, gen_loss))

      epoch_list.append(epoch+1)
      gen_loss_list.append(gen_loss)
      disc_loss_list.append(disc_loss)

    return np.array([epoch_list, gen_loss_list, disc_loss_list])

class InstanceNormalization(tf.keras.layers.Layer):
  """Instance Normalization Layer (https://arxiv.org/abs/1607.08022)."""

  def __init__(self, epsilon=1e-5):
    super(InstanceNormalization, self).__init__()
    self.epsilon = epsilon

  def build(self, input_shape):
    self.scale = self.add_weight(
        name='scale',
        shape=input_shape[-1:],
        initializer=tf.random_normal_initializer(1., 0.02),
        trainable=True)

    self.offset = self.add_weight(
        name='offset',
        shape=input_shape[-1:],
        initializer='zeros',
        trainable=True)

  def call(self, x):
    mean, variance = tf.nn.moments(x, axes=[1, 2], keepdims=True)
    inv = tf.math.rsqrt(variance + self.epsilon)
    normalized = (x - mean) * inv
    return self.scale * normalized + self.offset


def downsample(filters, size, norm_type='batchnorm', apply_norm=True):
  """Downsamples an input.

  Conv2D => Batchnorm => LeakyRelu

  Args:
    filters: number of filters
    size: filter size
    norm_type: Normalization type; either 'batchnorm' or 'instancenorm'.
    apply_norm: If True, adds the batchnorm layer

  Returns:
    Downsample Sequential Model
  """
  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
      tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                             kernel_initializer=initializer, use_bias=False))

  if apply_norm:
    if norm_type.lower() == 'batchnorm':
      result.add(tf.keras.layers.BatchNormalization())
    elif norm_type.lower() == 'instancenorm':
      result.add(InstanceNormalization())

  result.add(tf.keras.layers.LeakyReLU())

  return result


def upsample(filters, size, norm_type='batchnorm', apply_dropout=False):
  """Upsamples an input.

  Conv2DTranspose => Batchnorm => Dropout => Relu

  Args:
    filters: number of filters
    size: filter size
    norm_type: Normalization type; either 'batchnorm' or 'instancenorm'.
    apply_dropout: If True, adds the dropout layer

  Returns:
    Upsample Sequential Model
  """

  initializer = tf.random_normal_initializer(0., 0.02)

  result = tf.keras.Sequential()
  result.add(
      tf.keras.layers.Conv2DTranspose(filters, size, strides=2,
                                      padding='same',
                                      kernel_initializer=initializer,
                                      use_bias=False))

  if norm_type.lower() == 'batchnorm':
    result.add(tf.keras.layers.BatchNormalization())
  elif norm_type.lower() == 'instancenorm':
    result.add(InstanceNormalization())

  if apply_dropout:
    result.add(tf.keras.layers.Dropout(0.5))

  result.add(tf.keras.layers.ReLU())

  return result

def unet_generator(output_channels, norm_type='batchnorm'):
  """Modified u-net generator model (https://arxiv.org/abs/1611.07004).

  Args:
    output_channels: Output channels
    norm_type: Type of normalization. Either 'batchnorm' or 'instancenorm'.

  Returns:
    Generator model
  """

  down_stack = [
      downsample(64, 4, norm_type, apply_norm=False),  # (bs, 128, 128, 64)
      downsample(128, 4, norm_type),  # (bs, 64, 64, 128)
      downsample(256, 4, norm_type),  # (bs, 32, 32, 256)
      downsample(512, 4, norm_type),  # (bs, 16, 16, 512)
      downsample(512, 4, norm_type),  # (bs, 8, 8, 512)
      downsample(512, 4, norm_type),  # (bs, 4, 4, 512)
      downsample(512, 4, norm_type),  # (bs, 2, 2, 512)
      downsample(512, 4, norm_type),  # (bs, 1, 1, 512)
  ]

  up_stack = [
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 2, 2, 1024)
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 4, 4, 1024)
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 8, 8, 1024)
      upsample(512, 4, norm_type),  # (bs, 16, 16, 1024)
      upsample(256, 4, norm_type),  # (bs, 32, 32, 512)
      upsample(128, 4, norm_type),  # (bs, 64, 64, 256)
      upsample(64, 4, norm_type),  # (bs, 128, 128, 128)
  ]

  initializer = tf.random_normal_initializer(0., 0.02)
  last = tf.keras.layers.Conv2DTranspose(
      output_channels, 4, strides=2,
      padding='same', kernel_initializer=initializer,
      activation='tanh')  # (bs, 256, 256, 3)

  concat = tf.keras.layers.Concatenate()

  inputs = tf.keras.layers.Input(shape=[None, None, 3])
  x = inputs

  # Downsampling through the model
  skips = []
  for down in down_stack:
    x = down(x)
    skips.append(x)

  skips = reversed(skips[:-1])

  # Upsampling and establishing the skip connections
  for up, skip in zip(up_stack, skips):
    x = up(x)
    x = concat([x, skip])

  x = last(x)

  return tf.keras.Model(inputs=inputs, outputs=x)

def resunet_generator(output_channels, norm_type='batchnorm', resnet=None, depth=3):
  """Modified u-net generator model (https://arxiv.org/abs/1611.07004).

  Args:
    output_channels: Output channels
    norm_type: Type of normalization. Either 'batchnorm' or 'instancenorm'.
    resnet: Whether to apply SeResNet. Either None, 'SeResNet', or 'ResNet'.
    depth: Number of ResNet blocks for generator.

  Returns:
    Generator model
  """

  down_stack = [
      downsample(64, 4, norm_type, apply_norm=False),  # (bs, 128, 128, 64)
      downsample(128, 4, norm_type),  # (bs, 64, 64, 128)
      downsample(256, 4, norm_type),  # (bs, 32, 32, 256)
      downsample(512, 4, norm_type),  # (bs, 16, 16, 512)
      downsample(512, 4, norm_type),  # (bs, 8, 8, 512)
      downsample(512, 4, norm_type),  # (bs, 4, 4, 512)
      downsample(512, 4, norm_type),  # (bs, 2, 2, 512)
      downsample(512, 4, norm_type),  # (bs, 1, 1, 512)
  ]

  res_block = ResNet_Blocks(512, resnet, depth) # (bs, 1, 1, 512)

  up_stack = [
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 2, 2, 1024)
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 4, 4, 1024)
      upsample(512, 4, norm_type, apply_dropout=True),  # (bs, 8, 8, 1024)
      upsample(512, 4, norm_type),  # (bs, 16, 16, 1024)
      upsample(256, 4, norm_type),  # (bs, 32, 32, 512)
      upsample(128, 4, norm_type),  # (bs, 64, 64, 256)
      upsample(64, 4, norm_type),  # (bs, 128, 128, 128)
  ]

  initializer = tf.random_normal_initializer(0., 0.02)
  last = tf.keras.layers.Conv2DTranspose(
      output_channels, 4, strides=2,
      padding='same', kernel_initializer=initializer,
      activation='tanh')  # (bs, 256, 256, 3)

  concat = tf.keras.layers.Concatenate()

  inputs = tf.keras.layers.Input(shape=[None, None, 3])
  x = inputs

  # Downsampling through the model
  skips = []
  for down in down_stack:
    x = down(x)
    skips.append(x)

  skips = reversed(skips[:-1])

  # ResNet Blocks
  x = res_block(x)

  # Upsampling and establishing the skip connections
  for up, skip in zip(up_stack, skips):
    x = up(x)
    x = concat([x, skip])

  x = last(x)

  return tf.keras.Model(inputs=inputs, outputs=x)


def discriminator(norm_type='batchnorm', target=True):
  """PatchGan discriminator model (https://arxiv.org/abs/1611.07004).

  Args:
    norm_type: Type of normalization. Either 'batchnorm' or 'instancenorm'.
    target: Bool, indicating whether target image is an input or not.

  Returns:
    Discriminator model
  """

  initializer = tf.random_normal_initializer(0., 0.02)

  inp = tf.keras.layers.Input(shape=[None, None, 3], name='input_image')
  x = inp

  if target:
    tar = tf.keras.layers.Input(shape=[None, None, 3], name='target_image')
    x = tf.keras.layers.concatenate([inp, tar])  # (bs, 256, 256, channels*2)

  down1 = downsample(64, 4, norm_type, False)(x)  # (bs, 128, 128, 64)
  down2 = downsample(128, 4, norm_type)(down1)  # (bs, 64, 64, 128)
  down3 = downsample(256, 4, norm_type)(down2)  # (bs, 32, 32, 256)

  zero_pad1 = tf.keras.layers.ZeroPadding2D()(down3)  # (bs, 34, 34, 256)
  conv = tf.keras.layers.Conv2D(
      512, 4, strides=1, kernel_initializer=initializer,
      use_bias=False)(zero_pad1)  # (bs, 31, 31, 512)

  if norm_type.lower() == 'batchnorm':
    norm1 = tf.keras.layers.BatchNormalization()(conv)
  elif norm_type.lower() == 'instancenorm':
    norm1 = InstanceNormalization()(conv)

  leaky_relu = tf.keras.layers.LeakyReLU()(norm1)

  zero_pad2 = tf.keras.layers.ZeroPadding2D()(leaky_relu)  # (bs, 33, 33, 512)

  last = tf.keras.layers.Conv2D(
      1, 4, strides=1,
      kernel_initializer=initializer)(zero_pad2)  # (bs, 30, 30, 1)

  if target:
    return tf.keras.Model(inputs=[inp, tar], outputs=last)
  else:
    return tf.keras.Model(inputs=inp, outputs=last)

