# coding=utf-8
import os
import shutil
import sys
import time

import cv2
import numpy as np
import tensorflow as tf

cwd = os.getcwd()
sys.path.append(cwd)
os.chdir(cwd) 
print(os.getcwd())

from preprocess.preprocess import remove_border
from preprocess.preprocess import get_images
from ctpn.nets import model_train as model
from ctpn.utils.rpn_msr.proposal_layer import proposal_layer
from ctpn.utils.text_connector.detectors import TextDetector

tf.app.flags.DEFINE_string('test_data_path', '../data/demo-pid-red', '')
tf.app.flags.DEFINE_string('preprocess_output_path', 'preprocess/data/res', '')
tf.app.flags.DEFINE_string('ctpn_input_path', 'preprocess/data/res2', '')
tf.app.flags.DEFINE_string('ctpn_output_path', 'ctpn/data/res', '')
tf.app.flags.DEFINE_string('output_path', '../data/res/', '')
tf.app.flags.DEFINE_string('gpu', '0', '')
tf.app.flags.DEFINE_string('checkpoint_path', '../checkpoints_ctpn/', '')
FLAGS = tf.app.flags.FLAGS



def resize_image(img):
    img_size = img.shape
    im_size_min = np.min(img_size[0:2])
    im_size_max = np.max(img_size[0:2])

    im_scale = float(600) / float(im_size_min)
    if np.round(im_scale * im_size_max) > 1200:
        im_scale = float(1200) / float(im_size_max)
    #no scale is needed
    im_scale = 0.5
    new_h = int(img_size[0] * im_scale)
    new_w = int(img_size[1] * im_scale)
   
    new_h = new_h if new_h // 16 == 0 else (new_h // 16 + 1) * 16
    new_w = new_w if new_w // 16 == 0 else (new_w // 16 + 1) * 16
    re_im = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return re_im, (new_h / img_size[0], new_w / img_size[1])



def ctpn():
    if os.path.exists(FLAGS.ctpn_output_path):
        shutil.rmtree(FLAGS.ctpn_output_path)
    os.makedirs(FLAGS.ctpn_output_path)
    os.environ['CUDA_VISIBLE_DEVICES'] = FLAGS.gpu
    tf.reset_default_graph()
    with tf.get_default_graph().as_default():
        
        input_image = tf.placeholder(tf.float32, shape=[None, None, None, 3], name='input_image')
        input_im_info = tf.placeholder(tf.float32, shape=[None, 3], name='input_im_info')

        global_step = tf.get_variable('global_step', [], initializer=tf.constant_initializer(0), trainable=False)

        bbox_pred, cls_pred, cls_prob = model.model(input_image)

        variable_averages = tf.train.ExponentialMovingAverage(0.997, global_step)
        saver = tf.train.Saver(variable_averages.variables_to_restore())

        with tf.Session(config=tf.ConfigProto(allow_soft_placement=True)) as sess:
            ckpt_state = tf.train.get_checkpoint_state(FLAGS.checkpoint_path)
            model_path = os.path.join(FLAGS.checkpoint_path, os.path.basename(ckpt_state.model_checkpoint_path))
            saver.restore(sess, model_path)

            im_fn_list = get_images(FLAGS.ctpn_input_path)
            for im_fn in im_fn_list:
                print('===============')
                print(im_fn)
                start = time.time()
                try:
                    im = cv2.imread(im_fn)[:, :, ::-1]
                except:
                    print("Error reading image {}!".format(im_fn))
                    continue

                im, (rh, rw) = resize_image(im)
                h, w, c = im.shape
                print(h,w,c)
                img = im
                for im_rot in ['orig','rot90']:
                    if im_rot == 'rot90':
                        img = cv2.transpose(img)
                        img = cv2.flip(img,1)
                        bbox_color = (255,0,0)
                        im_info = np.array([w, h, c]).reshape([1, 3])
                    else: 
                        bbox_color = (0,255,0)
                        im_info = np.array([h, w, c]).reshape([1, 3])
                    bbox_pred_val, cls_prob_val = sess.run([bbox_pred, cls_prob],
                                                           feed_dict={input_image: [img],
                                                                      input_im_info: im_info})
    
                    textsegs, _ = proposal_layer(cls_prob_val, bbox_pred_val, im_info)
                    scores = textsegs[:, 0]
                    textsegs = textsegs[:, 1:5]

                    textdetector = TextDetector(DETECT_MODE='H')
                    boxes = textdetector.detect(textsegs, scores[:, np.newaxis], img.shape[:2])
                    boxes = np.array(boxes, dtype=np.int)

                    cost_time = (time.time() - start)
                    print("cost time: {:.2f}s".format(cost_time))

                    for i, box in enumerate(boxes):
                        if im_rot == 'rot90':
                            box = np.array([box[3],h-box[2],box[5],h-box[4],box[7],h-box[6],box[1],h-box[0],box[8]])
    
                        cv2.polylines(im, [box[:8].astype(np.int32).reshape((-1, 1, 2))], True, color=bbox_color,
                                      thickness=2)
                        # crop image with rectangle box and save
                        im_crop = im[x0:x0+w0, y0:y0+h0]
                        #cv2.imwrite(os.path.join(FLAGS.ctpn_output_path, im_rot+"-"+str(i)+"-"+os.path.basename(im_fn)), im[x0:x0+w0, y0:y0+h0])

                    
                    #im = cv2.resize(img, None, None, fx=1.0 / rh, fy=1.0 / rw, interpolation=cv2.INTER_LINEAR)
                    cv2.imwrite(os.path.join(FLAGS.ctpn_output_path, im_rot+"-"+os.path.basename(im_fn)),im[:, :, ::-1])

                    with open(os.path.join(FLAGS.ctpn_output_path, os.path.splitext(os.path.basename(im_fn))[0]) + ".txt",
                                "a") as f:
                        f.writelines("\n")
                        for i, box in enumerate(boxes):
                            line = ",".join(str(box[k]) for k in range(8))
                            line += "," + str(scores[i]) + "\r\n"
                            f.writelines(line)
                        f.close()

def main(argv=None):
    remove_border(FLAGS.test_data_path,FLAGS.preprocess_output_path)
    #ctpn()


if __name__ == '__main__':
    tf.app.run()