from keras.layers import Input, Lambda, Concatenate
import keras.backend as K
from keras.models import Model
import numpy as np


def DCGAN(generator_model, discriminator_model, input_img_dim, patch_dim, use_patch_gan_discrimator):
    """
    Here we do the following:
    1. Generate an image with the generator
    2. break up the generated image into patches
    3. feed the patches to a discriminator to get the avg loss across all patches
        (i.e is it fake or not)
    4. the DCGAN outputs the generated image and the loss

    This differs from standard GAN training in that we use patches of the image
    instead of the full image (although a patch size = img_size is basically the whole image)

    :param generator_model:
    :param discriminator_model:
    :param img_dim:
    :param patch_dim:
    :return: DCGAN model
    """
    print("input_img_dim:",input_img_dim)
    print("patch_dim:",patch_dim)
    generator_input = Input(shape=input_img_dim, name="DCGAN_input")
    
    # generated image model from the generator
    generated_image = generator_model(generator_input)
    print("generator_input:",generator_input)
    print("generated_image:",generated_image)
    if use_patch_gan_discrimator == True:
        #skip_concat3 = Concatenate()([upsamp6, conv1_2])
        # generated_image_new = K.concatenate([generated_image , generator_input] , axis=3)
        generated_image_new = Concatenate()([generated_image, generator_input])
        
    print("new_generated_image:",generated_image_new)
    h, w = input_img_dim[:2]
    ph, pw = patch_dim
    print("h,w,ph,pw:",h,w,ph,pw)

    # chop the generated image into patches
    list_row_idx = [(i * ph, (i + 1) * ph) for i in range(int(h / ph))]
    list_col_idx = [(i * pw, (i + 1) * pw) for i in range(int(w / pw))]
    print("list_row_idx:",list_row_idx)
    print("list_col_idx:",list_col_idx)
    list_gen_patch = []
    for row_idx in list_row_idx:
        for col_idx in list_col_idx:
            if use_patch_gan_discrimator == True:
                x_patch = Lambda(lambda z: z[:, row_idx[0]:row_idx[1], col_idx[0]:col_idx[1],
                    :], output_shape=input_img_dim)(generated_image_new)
                print("x_patch:",x_patch)
                list_gen_patch.append(x_patch)
                
            else:
                x_patch = Lambda(lambda z: z[:, row_idx[0]:row_idx[1], col_idx[0]:col_idx[1],
                    :], output_shape=input_img_dim)(generated_image)
                list_gen_patch.append(x_patch)
                print("x_patch:",x_patch)
   

    # measure loss from patches of the image (not the actual image)
    dcgan_output = discriminator_model(list_gen_patch)

    # actually turn into keras model
    dc_gan = Model(input=[generator_input], output=[generated_image, dcgan_output], name="DCGAN")
    return dc_gan
