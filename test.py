'''The main file for training a model

Usage:
    CUDA_VISIBLE_DEVICES=0 python3 test.py --trainer models_labelSmoothing.bc --config "output_bs24/vit_convpass/COI-M/M3_Q5_Mag10/RP10_lr0.0001_2-10040608/train_config.yaml" TEST.CKPT "output_bs24/vit_convpass/COI-M/M3_Q5_Mag10/RP10_lr0.0001_2-10040608/ckpt/best.ckpt" DATA.TEST "data/data_list/C+M+I-TEST.csv" TEST.NO_INFERENCE False DATA.NUM_FRAMES 1000
    
'''
from utils.metrics import metric_report_from_dict
import os
import logging
import numpy as np
import pandas as pd
import torch
from config.default import get_cfg_defaults
pd.set_option('display.max_columns', None)
import sklearn.metrics as metrics
torch.backends.cudnn.benchmark = True
import argparse
import importlib

def default_argument_parser():
    """
        Create arg parser
    """
    parser = argparse.ArgumentParser("Args parser for training")
    parser.add_argument("--config", default="", metavar="FILE", required=True, help="path to config file")
    parser.add_argument("--debug", action="store_true", help="enable debug mode")
    parser.add_argument("--trainer", default="", help="The trainer")
    #
    # parser.add_argument("--num-gpus", type=int, default=1, help="number of gpus *per machine*")
    parser.add_argument(
        "opts",
        help="Modify config options by adding 'KEY VALUE' pairs at the end of the command. "
             "See config references at "
             "https://detectron2.readthedocs.io/modules/config.html#config-references",
        default=None,
        nargs=argparse.REMAINDER,
    )
    return parser

def setup(args):
    """
        Perform some basic common setups at the beginning of a job, including:
    """
    cfg = get_cfg_defaults()

    trainer_lib = importlib.import_module(args.trainer)
    if 'custom_cfg' in trainer_lib.__all__:
        cfg.merge_from_other_cfg(trainer_lib.custom_cfg)

    if args.config:
        cfg.merge_from_file(args.config)

    if args.opts:
        cfg.merge_from_list(args.opts)

    assert cfg.TEST.CKPT, "A checkpoint should be provided"

    cfg.DEBUG = args.debug
    cfg.freeze()

    testing_output_dir = os.path.join(cfg.OUTPUT_DIR, 'test', cfg.TEST.TAG)

    if not os.path.exists(testing_output_dir):
        os.makedirs(testing_output_dir, exist_ok=True)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(filename)s-%(funcName)s-%(lineno)d:%(message)s",
                        datefmt='%a-%d %b %Y %H:%M:%S',
                        handlers=[logging.FileHandler(os.path.join(testing_output_dir, 'test.log'), 'a', 'utf-8'),
                                  logging.StreamHandler()]
                        )

    config_saved_path = os.path.join(testing_output_dir, "test_config.yaml")
    logging.info("Config:\n"+str(cfg))

    with open(config_saved_path, "w") as f:
        f.write(cfg.dump())
        logging.info("Full config saved to {}".format(config_saved_path))

    return trainer_lib, cfg


def toCSV(metrics,output_dir, path = './output_bs24/roseResult.csv'):
    metrics['output_path'] = output_dir
    df = pd.DataFrame(metrics, columns=['EER', 'MIN_HTER', 'AUC'], index=[metrics['output_path']])
    df.to_csv(path, mode='a', header=False)      


def main(trainer_lib, config):
    # config.CUDA = False
    trainer = trainer_lib.Trainer(config)
    trainer.set_trainMode(False)
    trainer.set_model()
    trainer.set_dataloader()

    assert config.TEST.CKPT; "Please provide the checkpoint for testing"
    trainer.load_checkpoint(config.TEST.CKPT)
    testing_output_dir = os.path.join(config.OUTPUT_DIR, 'test', config.TEST.TAG)
    thr = config.TEST.THR

    test_data_loader = trainer.test_loader

    npz_file_path = os.path.join(testing_output_dir, 'scores.npz')

    if config.TEST.NO_INFERENCE:
        npz = np.load(npz_file_path)
        scores_pred, scores_gt = npz['scores_pred'], npz['scores_gt']
    else:
        test_results = trainer.test(test_data_loader)
        scores_pred, scores_gt = test_results['scores_pred'], test_results['scores_gt']

    csv_file_path = os.path.join(testing_output_dir, config.TEST.TAG+'_scores_pred.csv')
    with open(csv_file_path, 'w') as f:
        for key in scores_pred.keys():
            output = str(key)+', '+str(scores_gt[key][0])+', '
            pred_1 = 0
            pred_0 = 0
            for i in scores_pred[key]:
                x = int(i+0.5)
                if x == 0: pred_0+=1
                elif x == 1: pred_1+=1
                else: 
                    print('i: ',i)
                    print('x: ',x)
            output += str(pred_0)+', '+str(pred_1)
            f.write("%s\n" % (output))

    # test_frame_metrics = metric_report(scores_pred,scores_gt, thr)
    test_frame_metrics, test_video_metrics = metric_report_from_dict(scores_gt, scores_pred, thr)
    df_frame = pd.DataFrame(test_frame_metrics, index=[0])
    df_video = pd.DataFrame(test_video_metrics, index=[0])
    logging.info("Frame level metrics:\n"+str(df_frame))
    logging.info("Video level metrics:\n"+str(df_video))
    # For better archive
    df_frame.to_csv(os.path.join(testing_output_dir, 'test_frame_metrics.csv'))
    df_video.to_csv(os.path.join(testing_output_dir, 'test_video_metrics.csv'))
    toCSV(test_frame_metrics, config.OUTPUT_DIR)


if __name__ == '__main__':
    
    parser = default_argument_parser()
    args = parser.parse_args()
    # pdb.set_trace()
    trainer_lib, config = setup(args)
    main(trainer_lib, config)
