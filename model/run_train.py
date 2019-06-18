from __future__ import print_function
from __future__ import division

import click
import json
import os
import logging
import numpy as np
from sklearn.utils import class_weight
from keras.optimizers import Adam
from keras.layers import Input
from keras.utils import to_categorical
from keras.models import Model

from models.DRUNet32f import get_model
from models.CNN import build_discriminator
from run_test import get_eval_metrics
from tools.augmentation import augmentation
from metrics import weighted_categorical_crossentropy
from keras.optimizers import Adam, RMSprop

os.environ['CUDA_VISIBLE_DEVICES'] = '1'


@click.command()
@click.argument('train_imgs_np_file', type=click.STRING)
@click.argument('train_masks_np_file', type=click.STRING)
@click.argument('output_weights_file', type=click.STRING)
@click.option('--pretrained_model',
              type=click.STRING,
              default='',
              help='path to the pretrained model')
@click.option('--use_augmentation',
              type=click.BOOL,
              default=False,
              help='use data augmentation or not')
@click.option('--use_weighted_crossentropy',
              type=click.BOOL,
              default=False,
              help='use weighting of classes according to inbalance or not')
@click.option('--test_imgs_np_file',
              type=click.STRING,
              default='',
              help='path to the numpy file of test image')
@click.option('--test_masks_np_file',
              type=click.STRING,
              default='',
              help='path to the numpy file of the test image')
@click.option(
    '--output_test_eval',
    type=click.STRING,
    default='',
    help='path to save results on test case evaluated per epoch of training')
def main(train_imgs_np_file,
         train_masks_np_file,
         output_weights_file,
         pretrained_model='',
         use_augmentation=False,
         use_weighted_crossentropy=False,
         test_imgs_np_file='',
         test_masks_np_file='',
         output_test_eval=''):
    assert (test_imgs_np_file != '' and test_masks_np_file != '') or \
           (test_imgs_np_file == '' and test_masks_np_file == ''), \
        'Both test image file and test mask file must be given'

    num_classes = 4
    if not use_augmentation:
        # total_epochs = 1000
        total_epochs = 100
    else:
        total_epochs = 50
    batch_size = 16
    learn_rate = 2e-4

    eval_per_epoch = (test_imgs_np_file != '' and test_masks_np_file != '')
    if eval_per_epoch:
        test_imgs = np.load(test_imgs_np_file)
        test_masks = np.load(test_masks_np_file)

    train_imgs = np.load(train_imgs_np_file)
    print("train_imgs:",train_imgs.shape)
    train_masks = np.load(train_masks_np_file)
    print("train_masks:",train_masks.shape)

    if use_weighted_crossentropy:
        class_weights = class_weight.compute_class_weight(
            'balanced', np.unique(train_masks), train_masks.flatten())

    channels_num = train_imgs.shape[-1]
    print("channels_num:", channels_num)
    img_shape = (train_imgs.shape[1], train_imgs.shape[2], channels_num)
    mask_shape = (train_masks.shape[1], train_masks.shape[2], num_classes)
    print("img_shape:", img_shape)
    print("mask_shape:", mask_shape)
    model = get_model(img_shape=img_shape, num_classes=num_classes)
    if pretrained_model != '':
        assert os.path.isfile(pretrained_model)
        model.load_weights(pretrained_model)

    if use_augmentation:
        samples_num = train_imgs.shape[0]
        images_aug = np.zeros(train_imgs.shape, dtype=np.float32)
        masks_aug = np.zeros(train_masks.shape, dtype=np.float32)
        for i in range(samples_num):
            images_aug[i], masks_aug[i] = augmentation(train_imgs[i],
                                                       train_masks[i])

        train_imgs = np.concatenate((train_imgs, images_aug), axis=0)
        train_masks = np.concatenate((train_masks, masks_aug), axis=0)
    print("train_masks,num_classes:",train_masks.shape, num_classes)
    train_masks_cat = to_categorical(train_masks, num_classes)
    print("train_masks_cat:",train_masks_cat.shape)


    if use_weighted_crossentropy:
        model.compile(optimizer=Adam(lr=(learn_rate)),
                      loss=weighted_categorical_crossentropy(class_weights))
    else:
        model.compile(optimizer=Adam(lr=(learn_rate)),
                      loss='categorical_crossentropy')
    # build model
    optimizer = RMSprop(lr=0.002, clipvalue=1.0, decay=1e-8)
    logging.basicConfig(filename='UNET_loss.log', level=logging.INFO)
    discriminator = build_discriminator(mask_shape)
    discriminator.compile(optimizer=optimizer, loss='binary_crossentropy')
    img = Input(shape=img_shape)
    rec_mask = model(img)
    
    discriminator.trainable = False
    validity = discriminator(rec_mask)

    adversarial_model = Model(img, [rec_mask, validity], name='D')
    adversarial_model.compile(loss=['binary_crossentropy', 'binary_crossentropy'],
        loss_weights=[0.2, 1],
        optimizer=optimizer)
    print('\n\runet')
    model.summary()
    print('\n\rdiscriminator')
    discriminator.summary()
    
    print('\n\radversarial_model')
    adversarial_model.summary()
    plot_epochs = []
    plot_g_recon_losses = []
    
    ones = np.ones((batch_size, 1))
    zeros = np.zeros((batch_size, 1))

    current_epoch = 1
    history = {}
    history['dsc'] = []
    history['h95'] = []
    history['vs'] = []
    
    while current_epoch <= total_epochs:
        print('Epoch', str(current_epoch), '/', str(total_epochs))
        batch_idxs = len(train_imgs) // batch_size
        print("len(train_imgs):",len(train_imgs))
        print("batch_idxs:",batch_idxs)
        for idx in range(0, batch_idxs):
            img_batch = train_imgs[idx * batch_size:(idx + 1) * batch_size]
            masks_cat_batch = train_masks_cat[idx * batch_size:(idx + 1) * batch_size]
            
            recon_masks_cat = model.predict(img_batch)

            d_loss_real = discriminator.train_on_batch(masks_cat_batch, ones)
            d_loss_fake = discriminator.train_on_batch(recon_masks_cat, zeros)

            adversarial_model.train_on_batch(img_batch, [masks_cat_batch, ones])
            g_loss = adversarial_model.train_on_batch(img_batch, [masks_cat_batch, ones])   
            plot_epochs.append(current_epoch+idx/batch_idxs)
            plot_g_recon_losses.append(g_loss[1])
            # model.fit(train_imgs,
            #         train_masks_cat,
            #         batch_size=batch_size,
            #         epochs=1,
            #         verbose=True,
            #         shuffle=True)
                    
            if eval_per_epoch and current_epoch % 10 == 0:
                model.save_weights(output_weights_file)
                pred_masks = model.predict(test_imgs)
                pred_masks = pred_masks.argmax(axis=3)
                dsc, h95, vs = get_eval_metrics(test_masks[:, :, :, 0], pred_masks)
                history['dsc'].append(dsc)
                history['h95'].append(h95)
                history['vs'].append(vs)
                print(dsc)
                print(h95)
                print(vs)
                if output_test_eval != '':
                    with open(output_test_eval, 'w+') as outfile:
                        json.dump(history, outfile)
            msg = 'Epoch:[{0}]-[{1}/{2}] --> d_loss: {3:>0.3f}, g_loss:{4:>0.3f},\
                        g_recon_loss:{5:>0.3f}'.format(current_epoch, idx, \
                        batch_idxs, d_loss_real+d_loss_fake, g_loss[0], g_loss[1])
            print(msg)
            logging.info(msg)
        current_epoch += 1
        
        
        # model.save_weights(output_weights_file)
    adversarial_model.save_weights(output_weights_file)
    pred_masks = model.predict(train_imgs)
    pred_masks = pred_masks.argmax(axis=3)
    dsc, h95, vs = get_eval_metrics(train_masks[:, :, :, 0], pred_masks)
    print(dsc)
    print(h95)
    print(vs)

    if output_test_eval != '':
        with open(output_test_eval, 'w+') as outfile:
            json.dump(history, outfile)


if __name__ == "__main__":
    main()
