import tensorflow as tf
from tensorflow.keras import layers

class ResNet_Block(layers.Layer):
  def __init__(self, filter_size=16, kernel_size=(3,3), strides=(1,1)):
    ''' args:
         filter_size: numbers of output filters.
         kernel_size: kernel_size. default is (3,3)
         strides: turple. If this is not (1,1), skip connection are replaced to convolution layer and it makes an output downsized.
    '''
    super(ResNet_Block, self).__init__()

    self.norm1 = layers.BatchNormalization()
    self.act1 = layers.Activation(tf.nn.relu)
    self.conv1 = layers.Conv2D(filter_size, kernel_size, strides=strides, padding='same')

    if strides == (1,1):
      self.shortcutblock = [layers.Identity()]
    else:
      self.shortcutblock = [
          layers.BatchNormalization(),
          layers.Activation(tf.nn.relu),
          layers.Conv2D(filter_size, (1,1), strides=strides, padding='same')
       ]

    self.norm2 = layers.BatchNormalization()
    self.act2 = layers.Activation(tf.nn.relu)
    self.conv2 = layers.Conv2D(filter_size, kernel_size, strides=(1,1), padding='same')

    self.add = layers.Add()

  def call(self, input):
    # Residual Block
    x = self.norm1(input, training=False)
    x = self.act1(x)
    x = self.conv1(x)

    x = self.norm2(x, training=False)
    x = self.act2(x)
    x = self.conv2(x)

    # Skip Connection Block
    skip = input
    for layer in self.shortcutblock:
      skip = layer(skip)

    x = self.add([x, skip])

    return x


class SE_Block(layers.Layer):
  def __init__(self, num_filters=16, ratio=16):
    ''' args:
         num_filters: numbers of output filters.
         kernel_size: kernel_size. default is (3,3)
         strides: turple. If this is not (1,1), skip connection are replaced to convolution layer and it makes an output downsized.
    '''
    super(SE_Block, self).__init__()

    self.num_filters = num_filters

    self.avepooling = layers.GlobalAveragePooling2D()
    self.dens1 = layers.Dense(num_filters//ratio, activation='relu')
    self.dens2 = layers.Dense(num_filters, activation='sigmoid')
    self.reshape = layers.Reshape((1, 1, num_filters))
    self.multiply = layers.Multiply()

  def call(self, input):
    x = self.avepooling(input)
    x = self.dens1(x)
    x = self.dens2(x)
    x = self.reshape(x)
    x = self.multiply([input, x])
    return x

class SEResNet_Block(layers.Layer):
  def __init__(self, filter_size=16, kernel_size=(3,3), strides=(1,1)):
    ''' args:
         filter_size: numbers of output filters.
         kernel_size: kernel_size. default is (3,3)
         strides: turple. If this is not (1,1), skip connection are replaced to convolution layer and it makes an output downsized.
    '''
    super(SEResNet_Block, self).__init__()

    self.norm1 = layers.BatchNormalization()
    self.act1 = layers.Activation(tf.nn.relu)
    self.conv1 = layers.Conv2D(filter_size, kernel_size, strides=strides, padding='same')

    if strides == (1,1):
      self.shortcutblock = [layers.Identity()]
    else:
      self.shortcutblock = [
          layers.BatchNormalization(),
          layers.Activation(tf.nn.relu),
          layers.Conv2D(filter_size, (1,1), strides=strides, padding='same')
       ]

    self.norm2 = layers.BatchNormalization()
    self.act2 = layers.Activation(tf.nn.relu)
    self.conv2 = layers.Conv2D(filter_size, kernel_size, strides=(1,1), padding='same')

    self.seblock = SE_Block(filter_size)

    self.add = layers.Add()

  def call(self, input):
    # Residual Block
    x = self.norm1(input, training=False)
    x = self.act1(x)
    x = self.conv1(x)

    x = self.norm2(x, training=False)
    x = self.act2(x)
    x = self.conv2(x)

    # SE block
    x = self.seblock(x)

    # Skip Connection Block
    skip = input
    for layer in self.shortcutblock:
      skip = layer(skip)

    x = self.add([x, skip])

    return x

def build_generator(
        latent_dim = 100, # Dimension of random noise (latent space vectors)
        image_size = (64, 64), # Image size
        channels = 3, # Number of channels of images
        num_filters = 64, # Number of filters for the last conv layer of the generator
        gen_kernel_size = (4, 4), # Kernel size for the generator
        activation='LeakyReLU', # Activation for the generator
        dense=True,
        resnet = '',
        ):
  
  '''Generator Model for DCGAN
  The generator uses tf.keras.layers.Conv2DTranspose (upsampling) layers to produce an image from a seed (random noise),
  which is a vector with the dimention of latent_dim.

  Start with a Dense layer that takes this seed as input.
  Project the output of the dense layer to a project_shape that is defined by project_size and channels.
  ex: project_size=[4, 4] and channels=3 make project_shape=[4, 4, 3].
  Upsample 4 times through Conv2DTranspose layer. This process generates an image that is 2 to the power of 4 times larger than the input.
  As project_shape=[4, 4, 3] the image generated has the shpae of [64, 64, 3].
  Notice the tf.keras.layers.LeakyReLU or the tf.keras.layers.ReLU activation for each layer, except the output layer which uses tanh.
  The default is ReLU.

  arguments:
    latent_dim: Int. Dimension of random noise (latent space vectors).
    image_size: Tuple. Image size with the sphape of (height, width).
    channels: Int. Number of channels of images
    num_filters: Int. Number of filters for the 1st conv layer of the discriminator.
    gen_kernel_size: Tuple. Kernel size for the generator
    activation: str: Str, the activation functions for each layer except the output layer. If you specify "LeakyReLU", the activations are LeakyReLU, otherwise ReLU.
    dense: Boolean, whether the 1st layer is a Dense layer. If False, the 1st layer is a Conv2DTranspose layer.
    resnet: Str, ResNet is adopted when 'Res', SEResnet is adopted when 'SE', None is none adopt.
  '''
  # Project size
  project_size = [x//16 for x in image_size]
  # Project shape
  project_shape = project_size + [num_filters*16]
  dense_units = project_size[0] * project_size[1] * num_filters*16

  model = tf.keras.Sequential()
  
  if dense:
    model.add(tf.keras.layers.Dense(dense_units, use_bias=False, input_dim=latent_dim))
  else:
    model.add(tf.keras.layers.Input(shape=(latent_dim)))
    model.add(tf.keras.layers.Reshape((1,1,latent_dim)))
    model.add(tf.keras.layers.Conv2DTranspose(num_filters*16, project_size, strides=(1, 1), padding='valid', use_bias=False))
  model.add(tf.keras.layers.BatchNormalization())
  if 'leakyrelu' == activation.lower():
    activation_layer = tf.keras.layers.LeakyReLU()
  else:
    activation_layer = tf.keras.layers.ReLU()
  model.add(activation_layer)
  model.add(tf.keras.layers.Reshape(project_shape))

  # ResNet
  if 'se' in resnet.lower():
    pass
  elif 'res' in resnet.lower():
    model.add(ResNet_Block(num_filters*16))
  else:
    pass


  # conv1
  model.add(tf.keras.layers.Conv2DTranspose(num_filters*8, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False))
  model.add(tf.keras.layers.BatchNormalization())
  if 'leakyrelu' == activation.lower():
    activation_layer = tf.keras.layers.LeakyReLU()
  else:
    activation_layer = tf.keras.layers.ReLU()
  model.add(activation_layer)

  # conv2
  model.add(tf.keras.layers.Conv2DTranspose(num_filters*4, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False))
  model.add(tf.keras.layers.BatchNormalization())
  if 'leakyrelu' == activation.lower():
    activation_layer = tf.keras.layers.LeakyReLU()
  else:
    activation_layer = tf.keras.layers.ReLU()
  model.add(activation_layer)
      
  # conv4
  model.add(tf.keras.layers.Conv2DTranspose(num_filters*2, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False))
  model.add(tf.keras.layers.BatchNormalization())
  if 'leakyrelu' == activation.lower():
    activation_layer = tf.keras.layers.LeakyReLU()
  else:
    activation_layer = tf.keras.layers.ReLU()
  model.add(activation_layer)
      
  # conv5
  model.add(tf.keras.layers.Conv2DTranspose(channels, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False, activation='tanh'))

  return model


def build_discriminator(
        image_size = (64, 64), # Image size
        channels = 3, # Number of channels of images
        num_filters = 64, # Number of filters for the 1st conv layer of the discriminator
        disc_kernel_size = (4, 4), # Kernel size for the discriminator
        dropout_rate = 0.4, # Dropout rate for the discriminator
        batchnorm=False, 
        dropout=True, 
        dense=True,
        pooling=None,
        ):
  '''The Discriminator
  The discriminator is a CNN-based image classifier.
  Use the (as yet untrained) discriminator to classify the generated images as real or fake.
  The model will be trained to output positive values for real images, and negative values for fake images.

  arguments:
    image_size: Tuple. Image size with the sphape of (height, width).
    channels: Int. Number of channels of images.
    num_filters: Int. Number of filters for the 1st conv layer of the discriminator.
    disc_kernel_size: Tuple. Kernel size for the discriminator.
    dropout_rate: Float. Dropout rate for the discriminator.
    batchnorm: Boolean, whether add Batchnormalization.
    dropout: Boolean, whether add Dropout.
    dense: Boolean, whether use a Dense layer for output. If False, the last output layer is a Conv2D layer. 
  '''
  # Input Shape
  input_shape = list(image_size) + [channels]

  model = tf.keras.Sequential()

  if pooling:
    strides=(1,1)
  else:
    strides=(2,2)

  # conv1
  model.add(tf.keras.layers.Conv2D(num_filters, disc_kernel_size, strides=strides, padding='same', input_shape=input_shape))
  if pooling == 'max':
    model.add(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
  elif pooling:
    model.add(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

  model.add(tf.keras.layers.LeakyReLU())

  if dropout:
    model.add(tf.keras.layers.Dropout(dropout_rate))

  # conv2
  model.add(tf.keras.layers.Conv2D(num_filters*2, disc_kernel_size, strides=strides, padding='same'))
  if pooling == 'max':
    model.add(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
  elif pooling:
    model.add(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))
  
  if batchnorm:
    model.add(tf.keras.layers.BatchNormalization())
  
  model.add(tf.keras.layers.LeakyReLU())
  
  if dropout:
    model.add(tf.keras.layers.Dropout(dropout_rate))

  # conv3
  model.add(tf.keras.layers.Conv2D(num_filters*4, disc_kernel_size, strides=strides, padding='same'))
  if pooling == 'max':
    model.add(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
  elif pooling:
    model.add(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

  if batchnorm:
    model.add(tf.keras.layers.BatchNormalization())

  model.add(tf.keras.layers.LeakyReLU())

  if dropout:
    model.add(tf.keras.layers.Dropout(dropout_rate))

  # conv4
  model.add(tf.keras.layers.Conv2D(num_filters*8, disc_kernel_size, strides=strides, padding='same'))
  if pooling == 'max':
    model.add(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
  elif pooling:
    model.add(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

  if batchnorm:
    model.add(tf.keras.layers.BatchNormalization())

  model.add(tf.keras.layers.LeakyReLU())

  if dropout:
    model.add(tf.keras.layers.Dropout(dropout_rate))

  # Output
  if dense:
    model.add(tf.keras.layers.Flatten())
    model.add(tf.keras.layers.Dense(1))
  else:
    model.add(tf.keras.layers.Conv2D(1, disc_kernel_size, strides=(2, 2), padding='valid'))
    model.add(tf.keras.layers.GlobalAveragePooling2D())

  return model


class SEResNet_generator(tf.keras.Model):
  '''Generator Model for DCGAN with SE-ResNet
  A Deep Convolutional(DC) generator uses tf.keras.layers.Conv2DTranspose (upsampling) layers to produce an image from a seed (random noise), 
  which is a vector with the dimension of latent_dim. This generator is improved with adding SE-ResNet blocks.

  arguments:
    latent_dim: Int. Dimension of random noise (latent space vectors).
    image_size: Tuple. Image size with the sphape of (height, width).
    channels: Int. Number of channels of images
    num_filters: Int. Number of filters for the 1st conv layer of the discriminator.
    gen_kernel_size: Tuple. Kernel size for the generator
    activation: str: Str, the activation functions for each layer except the output layer. If you specify "LeakyReLU", the activations are LeakyReLU, otherwise ReLU.
    dense: Boolean, whether the 1st layer is a Dense layer. If False, the 1st layer is a Conv2DTranspose layer.
    resnet: Str, ResNet is adopted when 'Res', SEResnet is adopted when 'SE', None is none adopt.
  '''
  def __init__(self,
          latent_dim = 100, # Dimension of random noise (latent space vectors)
          image_size = (64, 64), # Image size
          channels = 3, # Number of channels of images
          num_filters = 64, # Number of filters for the last conv layer of the generator
          gen_kernel_size = (4, 4), # Kernel size for the generator
          activation='LeakyReLU', # Activation for the generator
          dense=True,
          resnet = '',
          num_blocks=[3,3,3], # List of number of blocks               
          ):
    super().__init__()
    # Project size
    project_size = [x//16 for x in image_size]
    # Project shape
    project_shape = project_size + [num_filters*16]
    dense_units = project_size[0] * project_size[1] * num_filters*16

    if dense:
      self.initial_block=[
          tf.keras.layers.Dense(dense_units, use_bias=False, input_dim=latent_dim)
      ]
    else:
      self.initial_block=[
          tf.keras.layers.Input(shape=(latent_dim)),
          tf.keras.layers.Reshape((1,1,latent_dim)),
          tf.keras.layers.Conv2DTranspose(num_filters*16, project_size, strides=(1, 1), padding='valid', use_bias=False),
      ]

    norm = tf.keras.layers.BatchNormalization()
    if 'leakyrelu' == activation.lower():
      act = tf.keras.layers.LeakyReLU()
    else:
      act = tf.keras.layers.ReLU()
    reshape = tf.keras.layers.Reshape(project_shape)

    self.initial_block.extend([norm, act, reshape])

    # ResNet Block 1
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*16) for _ in range(num_blocks[0])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*16) for _ in range(num_blocks[0])
      ]
    else:
      block = []
    self.res_block1 = block

    # conv block1
    conv = tf.keras.layers.Conv2DTranspose(num_filters*8, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False)
    norm = tf.keras.layers.BatchNormalization()
    if 'leakyrelu' == activation.lower():
      act = tf.keras.layers.LeakyReLU()
    else:
      act = tf.keras.layers.ReLU()
    self.conv_block1 = [conv, norm, act]

    # ResNet Block 2
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*8) for _ in range(num_blocks[1])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*8) for _ in range(num_blocks[1])
      ]
    else:
      block = []
    self.res_block2 = block

    # conv2
    conv = tf.keras.layers.Conv2DTranspose(num_filters*4, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False)
    norm = tf.keras.layers.BatchNormalization()
    if 'leakyrelu' == activation.lower():
      act = tf.keras.layers.LeakyReLU()
    else:
      act = tf.keras.layers.ReLU()
    self.conv_block2 = [conv, norm, act]

    # ResNet Block 3
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*4) for _ in range(num_blocks[2])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*4) for _ in range(num_blocks[2])
      ]
    else:
      block = []
    self.res_block3 = block

    # conv3
    conv = tf.keras.layers.Conv2DTranspose(num_filters*2, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False)
    norm = tf.keras.layers.BatchNormalization()
    if 'leakyrelu' == activation.lower():
      act = tf.keras.layers.LeakyReLU()
    else:
      act = tf.keras.layers.ReLU()
    self.conv_block3 = [conv, norm, act]

    # conv4
    conv = tf.keras.layers.Conv2DTranspose(channels, gen_kernel_size, strides=(2, 2), padding='same', use_bias=False, activation='tanh')
    self.conv_block4 = [conv]

  def call(self, x):
    for layer in self.initial_block:
      x = layer(x)
    for layer in self.res_block1:
      x = layer(x)
    for layer in self.conv_block1:
      x = layer(x)
    for layer in self.res_block2:
      x = layer(x)
    for layer in self.conv_block2:
      x = layer(x)
    for layer in self.res_block3:
      x = layer(x)
    for layer in self.conv_block3:
      x = layer(x)
    for layer in self.conv_block4:
      x = layer(x)
    return x

class SEResNet_discriminator(tf.keras.Model):
  '''The Discriminator
  The discriminator is a CNN-based image classifier.
  Use the (as yet untrained) discriminator to classify the generated images as real or fake.
  The model will be trained to output positive values for real images, and negative values for fake images.

  arguments:
    image_size: Tuple. Image size with the sphape of (height, width).
    channels: Int. Number of channels of images.
    num_filters: Int. Number of filters for the 1st conv layer of the discriminator.
    disc_kernel_size: Tuple. Kernel size for the discriminator.
    dropout_rate: Float. Dropout rate for the discriminator.
    batchnorm: Boolean, whether add Batchnormalization.
    dropout: Boolean, whether add Dropout.
    dense: Boolean, whether use a Dense layer for output. If False, the last output layer is a Conv2D layer.
  '''
  def __init__(self,
        image_size = (64, 64), # Image size
        channels = 3, # Number of channels of images
        num_filters = 64, # Number of filters for the 1st conv layer of the discriminator
        disc_kernel_size = (4, 4), # Kernel size for the discriminator
        dropout_rate = 0.4, # Dropout rate for the discriminator
        batchnorm=False,
        dropout=True,
        dense=True,
        pooling=None,
        resnet = '',
        num_blocks = [1,0,0,0]
        ):
    super().__init__()

    # Input Shape
    input_shape = list(image_size) + [channels]


    if pooling:
      strides=(1,1)
    else:
      strides=(2,2)

    # conv1
    self.conv_block1 = [tf.keras.layers.Conv2D(num_filters, disc_kernel_size, strides=strides, padding='same', input_shape=input_shape)]
    if pooling == 'max':
      self.conv_block1.append(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
    elif pooling:
      self.conv_block1.append(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

    self.conv_block1.append(tf.keras.layers.LeakyReLU())

    if dropout:
      self.conv_block1.append(tf.keras.layers.Dropout(dropout_rate))

    # ResNet Block 1
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters) for _ in range(num_blocks[0])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters) for _ in range(num_blocks[0])
      ]
    else:
      block = []
    self.res_block1 = block

    # conv2
    self.conv_block2 = [tf.keras.layers.Conv2D(num_filters*2, disc_kernel_size, strides=strides, padding='same')]
    if pooling == 'max':
      self.conv_block2.append(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
    elif pooling:
      self.conv_block2.append(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

    if batchnorm:
      self.conv_block2.append(tf.keras.layers.BatchNormalization())

    self.conv_block2.append(tf.keras.layers.LeakyReLU())

    if dropout:
      self.conv_block2.append(tf.keras.layers.Dropout(dropout_rate))

    # ResNet Block 2
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*2) for _ in range(num_blocks[1])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*2) for _ in range(num_blocks[1])
      ]
    else:
      block = []
    self.res_block2 = block

    # conv3
    self.conv_block3 = [tf.keras.layers.Conv2D(num_filters*4, disc_kernel_size, strides=strides, padding='same')]
    if pooling == 'max':
      self.conv_block3.append(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
    elif pooling:
      self.conv_block3.append(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

    if batchnorm:
      self.conv_block3.append(tf.keras.layers.BatchNormalization())

    self.conv_block3.append(tf.keras.layers.LeakyReLU())

    if dropout:
      self.conv_block3.append(tf.keras.layers.Dropout(dropout_rate))
    
    # ResNet Block 3
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*4) for _ in range(num_blocks[2])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*4) for _ in range(num_blocks[2])
      ]
    else:
      block = []
    self.res_block3 = block

    # conv4
    self.conv_block4 = [tf.keras.layers.Conv2D(num_filters*8, disc_kernel_size, strides=strides, padding='same')]
    if pooling == 'max':
      self.conv_block4.append(tf.keras.layers.MaxPooling2D(pool_size=(2, 2)))
    elif pooling:
      self.conv_block4.append(tf.keras.layers.AveragePooling2D(pool_size=(2, 2)))

    if batchnorm:
      self.conv_block4.append(tf.keras.layers.BatchNormalization())

    self.conv_block4.append(tf.keras.layers.LeakyReLU())

    if dropout:
      self.conv_block4.append(tf.keras.layers.Dropout(dropout_rate))

    # ResNet Block 4
    if 'se' in resnet.lower():
      block = [
          SEResNet_Block(num_filters*8) for _ in range(num_blocks[3])
      ]
    elif 'res' in resnet.lower():
      block = [
          ResNet_Block(num_filters*8) for _ in range(num_blocks[3])
      ]
    else:
      block = []
    self.res_block4 = block

    # Header block
    if dense:
      self.header_block = [tf.keras.layers.Flatten(), tf.keras.layers.Dense(1)]
    else:
      self.header_block = [tf.keras.layers.Conv2D(1, disc_kernel_size, strides=(2, 2), padding='valid'), tf.keras.layers.GlobalAveragePooling2D()]

  def call(self, x):
    for layer in self.conv_block1:
      x = layer(x)
    for layer in self.res_block1:
      x = layer(x)
    for layer in self.conv_block2:
      x = layer(x)
    for layer in self.res_block2:
      x = layer(x)
    for layer in self.conv_block3:
      x = layer(x)
    for layer in self.res_block3:
      x = layer(x)
    for layer in self.conv_block4:
      x = layer(x)
    for layer in self.res_block4:
      x = layer(x)
    for layer in self.header_block:
      x = layer(x)
    return x


