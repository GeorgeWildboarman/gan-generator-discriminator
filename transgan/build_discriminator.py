import tensorflow as tf
from tensorflow.keras import layers

from transgan.vit_helper import MLP_layer, WindowPartition_layer, WindowReverse_layer, SelfAttention_layer
  

class Block(layers.Layer):
  '''Transformer block.

    Args:
        embed_dim: Int. Embeddinig dimension.
        num_heads: Int. Number of attention heads.
        mlp_ratio: Int, the factor for determination of the hidden dimension size of the MLP module with respect
        to embed_dim.
        mlp_p: Float. Dropout probability applied to the MLP.
        qkv_bias: Boolean, whether the dense layers use bias vectors/matrices in MultiHeadAttention.
        attn_p : Float. Dropout probability applied to MultiHeadAttention.
        proj_p : Float. Dropout probability applied to the output tensor.
        activation: String. Activation function to use in MLP.

  '''
  def __init__(self, embed_dim, num_heads=4, mlp_ratio=4, mlp_p=0., qkv_bias=False, attn_p=0., proj_p=0., activation='gelu'):
    super().__init__()

    self.LN1 = layers.LayerNormalization(epsilon=1e-6)

    # self.MHA = layers.MultiHeadAttention(num_heads=num_heads, key_dim=embed_dim, use_bias=qkv_bias, dropout=attn_p,)
    self.attention = SelfAttention_layer(dim=embed_dim, num_heads=num_heads, qkv_bias=qkv_bias, attn_p=attn_p, proj_p=proj_p)

    self.LN2 = layers.LayerNormalization(epsilon=1e-6)

    hidden_units = [embed_dim * mlp_ratio, embed_dim]
    self.MLP = MLP_layer(hidden_units=hidden_units, dropout_rate=mlp_p, activation='gelu')

  def call(self, encoded_patches):
    # Layer normalization 1.
    x1 = self.LN1(encoded_patches)

    # Create a multi-head attention layer.
    # attention_output = self.MHA(x1, x1)
    attention_output = self.attention(x1)
    
    # Skip connection 1.
    x2 = layers.Add()([attention_output, encoded_patches])

    # Layer normalization 2.
    x3 = self.LN2(x2)
    
    # MLP.
    x3 = self.MLP(x3)
    
    # Skip connection 2.
    out = layers.Add()([x3, x2])

    return out

class PatchEmbed_layer(layers.Layer):
  '''Divide an image into patches

    As ViT operates on sequences, you need to tokenize the images into sequences of tokens.
    Each token represents a specific region or patch of the image. You can divide the image 
    into a grid of patches and flatten each patch into a single token. Additionally, 
    add a special "classification" token at the beginning to indicate the task.

    The approach to divide an image into patches is by using a convolutional layer (Conv2D) as part of the tokenization process. 
    This approach can be seen as a form of patch extraction using a sliding window technique.

     Sliding Window Patch Extraction: Use a Conv2D layer with a sliding window approach to extract patches from the image. 
     The Conv2D layer acts as a local feature extractor, similar to how it is used in convolutional neural networks.

      > Configure the Conv2D layer with appropriate kernel size, stride, and padding.
      > The kernel size determines the patch size you want to extract.
      > The stride determines the amount of overlap between patches.
      > Padding can be used to ensure that patches are extracted from the entire image.

    Positional Encoding: As ViT doesn't encode spatial information inherently, you need to include positional encodings for each token. 
    The positional encodings represent the position or order of the tokens within the sequence. You can use sine and cosine functions or 
    learnable embeddings to generate these positional encodings.


  Args:
    image_size: Tuple. Size of the image wiht the shape (Height, Width).
    patch_size: Int. Size of the patch.
    num_patches: the number of patches in one image
    embed_dim: the size of a vector that each patch is projected.
    kernel_size: Int or tuple/list of 2 integers, specifying the height and width of the 2D convolution window.
    
  Returns:
    A tf.tensor with the shape of (batches, num patches, embed dimension)

  '''

  def __init__(self, image_size, patch_size, embed_dim, kernel_size, padding='valid', add_pos=False):
    super().__init__()
    self.embed_dim = embed_dim
    self.num_patches = num_patches = (image_size[0]//patch_size)*(image_size[1]//patch_size)
    self.add_pos = add_pos

    # Split into patches and Project to a vector with embed dimensional. 
    self.projection = tf.keras.layers.Conv2D(filters=embed_dim, kernel_size=kernel_size, strides=patch_size, padding=padding)

    # Position Embed
    if add_pos:
      self.pos_embed = tf.Variable(tf.zeros((1, num_patches, embed_dim), dtype=tf.dtypes.float32))
    
  def call(self, images):
    # batch_size = tf.shape(images)[0]
    batch_size = images.shape[0]
    x = self.projection(images)
    x = tf.reshape(x, (batch_size, -1, self.embed_dim))
    if self.add_pos:
      x = x + self.pos_embed
    return x

class AddPositionEmbed_layer(layers.Layer):
  def __init__(self, num_patches, embed_dim):
    super().__init__()
    self.pos_embed = tf.Variable(tf.zeros((1, num_patches, embed_dim), dtype=tf.dtypes.float32))

  def call(self, x):
    return x + self.pos_embed

class AddCLSToken_layer(layers.Layer):
  def __init__(self, embed_dim):
    super().__init__()
    self.cls_token = tf.Variable(tf.zeros((1, 1, embed_dim), dtype=tf.dtypes.float32))

  def call(self, x):
    batch_size = x.shape[0]
    return tf.concat([tf.tile(self.cls_token, [batch_size, 1, 1]), x], axis=1)


class discriminator(tf.keras.Model):
  '''Discriminator with a Vision Transformer (ViT).
  Building a discriminator with a Vision Transformer (ViT) involves adapting 
  the transformer architecture to perform binary classification tasks on image data.

  In a Vision Transformer (ViT), the primary components include self-attention mechanisms, 
  transformer encoder layers, position embeddings, and classification heads. Each component:

  Self-Attention Mechanisms: Self-attention is a key component in transformers, including ViTs. 
    Self-attention allows the model to capture relationships between different tokens within 
    a sequence. It calculates attention weights for each token based on its relation to other tokens, 
    enabling the model to focus on relevant information during processing.

  Transformer Encoder Layers: ViTs consist of multiple transformer encoder layers stacked on 
    top of each other. Each transformer encoder layer consists of two sub-layers: 
    a multi-head self-attention mechanism and a feed-forward neural network. 
    The self-attention mechanism captures the dependencies between tokens, 
    while the feed-forward network applies non-linear transformations to each token independently.

  Position Embeddings: Position embeddings encode the spatial information of each token within 
    the image sequence. Since ViTs do not have built-in positional information like CNNs, position 
    embeddings are added to the input tokens to indicate their relative positions. Commonly, 
    sine and cosine functions or learnable embeddings are used to generate position embeddings.

  Classification Head: A classification head is added to the output of the ViT model to perform 
    the final task-specific prediction. For binary classification tasks like discrimination, 
    the classification head typically consists of a fully connected layer followed by 
    a sigmoid activation function to produce the binary classification output.
  
    Args:
      image_size: Turple.
      depth: Int. The number of transformer blocks.
      num_classes: Int. The number of classes.
      embed_dim: Int. Embeddinig dimension.
      patch_siz: Int.
      mlp_p: Float. Dropout probability applied to the MLP.
      num_heads: Int. Number of attention heads.
      mlp_ratio: Int, the factor for determination of the hidden dimension size of the MLP module with respect to embed_dim.
      attn_p : Float. Dropout probability applied to MultiHeadAttention.
      window_size: Int, grid size for grid transformer block.
        
        
  '''

  def __init__(
      self,
      image_size = (64, 64),
      depth = 3,
      num_classes = 1,
      embed_dim = 384,
      patch_size = 2,
      mlp_p = 0.,
      num_heads = 4,
      mlp_ratio = 4,
      attn_p = 0.,
      window_size = 4,
      ):
    
    super().__init__()

    self.patch_size = patch_size

    self.embed_dim = embed_dim
    self.embed_dim_1 = embed_dim_1 = embed_dim//4
    self.embed_dim_2 = embed_dim_2 = embed_dim//4
    self.embed_dim_3 = embed_dim_3 = embed_dim//2

    self.patch_size_1 = patch_size_1 = patch_size
    self.patch_size_2 = patch_size_2 = patch_size*2
    self.patch_size_3 = patch_size_3 = patch_size*4

    self.patches_1 = PatchEmbed_layer(image_size, patch_size = patch_size_1, embed_dim = embed_dim_1, kernel_size = patch_size_1*2, padding='same')
    self.patches_2 = PatchEmbed_layer(image_size, patch_size = patch_size_2, embed_dim = embed_dim_2, kernel_size = patch_size_2, padding='valid')
    self.patches_3 = PatchEmbed_layer(image_size, patch_size = patch_size_3, embed_dim = embed_dim_3, kernel_size = patch_size_3, padding='valid')

    num_patches_1 = self.patches_1.num_patches
    num_patches_2 = self.patches_2.num_patches
    num_patches_3 = self.patches_3.num_patches

    self.add_pos_embed_1 = AddPositionEmbed_layer(num_patches_1, embed_dim_1)
    self.add_pos_embed_2 = AddPositionEmbed_layer(num_patches_2, embed_dim_2)
    self.add_pos_embed_3 = AddPositionEmbed_layer(num_patches_3, embed_dim_3)

    self.window_size = window_size

    self.blocks_1 = [
        Block(
            embed_dim=embed_dim_1, num_heads=num_heads, mlp_ratio=mlp_ratio, mlp_p=mlp_p, qkv_bias=False, attn_p=attn_p, activation='gelu'
        ) for _ in range(depth)
    ]
    
    self.blocks_2 = [
        Block(
            embed_dim=embed_dim_1+embed_dim_2, num_heads=num_heads, mlp_ratio=mlp_ratio, mlp_p=mlp_p, qkv_bias=False, attn_p=attn_p, activation='gelu'
        ) for _ in range(depth-1)
    ]
    
    self.blocks_21 = [
        Block(
            embed_dim=embed_dim_1+embed_dim_2, num_heads=num_heads, mlp_ratio=mlp_ratio, mlp_p=mlp_p, qkv_bias=False, attn_p=attn_p, activation='gelu'
        ) for _ in range(1)
    ]
    
    self.blocks_3 = [
        Block(
            embed_dim=embed_dim, num_heads=num_heads, mlp_ratio=mlp_ratio, mlp_p=mlp_p, qkv_bias=False, attn_p=attn_p, activation='gelu'
        ) for _ in range(depth)
    ]


    self.add_cls_token = AddCLSToken_layer(embed_dim=embed_dim)

    self.blocks_last = [
        Block(
            embed_dim=embed_dim, num_heads=num_heads, mlp_ratio=mlp_ratio, mlp_p=mlp_p, qkv_bias=False, attn_p=attn_p, activation='gelu'
        )
    ]

    self.layer_norm = layers.LayerNormalization(epsilon=1e-6)

    self.head = layers.Dense(num_classes)

  def call(self, input):
    batch_size, height, width, channels = input.shape
    h = height//self.patch_size_1
    w = width//self.patch_size_1

    x_1 = self.patches_1(input)
    x_2 = self.patches_2(input)
    x_3 = self.patches_3(input)

    # B, H//2*W//2, embed_dim//4 if patch_size = 2
    x = self.add_pos_embed_1(x_1)
    c = x.shape[-1]

    # -- Grid Transformer Block --
    # B, H//2, W//2, embed_dim//4 if patch_size = 2
    x = layers.Reshape((h, w, c))(x)
    x = WindowPartition_layer(self.window_size)(x)
    for block in self.blocks_1:
      x = block(x)
    x = WindowReverse_layer(self.window_size, h, w)(x)

    # -- 2x AvePool --
    # B, H//4, W//4, embed_dim//4
    x = layers.AveragePooling2D(2)(x)
    _, h, w, c = x.shape

    #  -- Concatnate --
    # B, H//4*W//4, embed_dim//4
    x = layers.Reshape((-1, c))(x)
    # B, H//4*W//4, embed_dim//2
    x = layers.Concatenate(axis=-1)([x, x_2])
    c = x.shape[-1]

    # -- Grid Transformer Block --
    x = layers.Reshape((h, w, c))(x)
    x = WindowPartition_layer(self.window_size)(x)
    for block in self.blocks_2:
      x = block(x)
    x = WindowReverse_layer(self.window_size, h, w)(x)    
    # -- Transformer Block --
    x = layers.Reshape((h*w, c))(x)
    for block in self.blocks_21:
      x = block(x)

    # -- 2x AvePool --
    x = layers.Reshape((h, w, c))(x)
    # B, H//8, W//8, embed_dim//2
    x = layers.AveragePooling2D(2)(x)
    _, h, w, c = x.shape

    #  -- Concatnate --
    x = layers.Reshape((-1, c))(x)
    # B, H//8*W//8, embed_dim
    x = layers.Concatenate(axis=-1)([x, x_3])
    c = x.shape[-1]

    # -- Transformer Block --
    for block in self.blocks_3:
      x = block(x)

    # -- Add CLS token --
    # B, H//8*W//8+1, embed_dim
    x = self.add_cls_token(x)

    # -- Transformer Block --
    for block in self.blocks_last:
      x = block(x)

    x = self.layer_norm(x)
    x = self.head(x[:,0])

    return x
