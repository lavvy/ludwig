#! /usr/bin/env python
# coding=utf-8
# Copyright (c) 2019 Uber Technologies, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import logging
import os
import sys
from pprint import pformat

import yaml

from ludwig.data.preprocessing import preprocess_for_training
from ludwig.features.feature_registries import input_type_registry
from ludwig.features.feature_registries import output_type_registry
from ludwig.globals import LUDWIG_VERSION
from ludwig.models.model import Model
from ludwig.models.model import load_model_and_definition
from ludwig.utils.data_utils import save_json
from ludwig.utils.defaults import default_random_seed
from ludwig.utils.defaults import merge_with_defaults
from ludwig.utils.misc import get_experiment_description
from ludwig.utils.misc import get_from_registry
from ludwig.utils.print_utils import logging_level_registry
from ludwig.utils.print_utils import print_boxed
from ludwig.utils.print_utils import print_ludwig


def full_train(
        model_definition,
        model_definition_file=None,
        data_csv=None,
        data_train_csv=None,
        data_validation_csv=None,
        data_test_csv=None,
        data_hdf5=None,
        data_train_hdf5=None,
        data_validation_hdf5=None,
        data_test_hdf5=None,
        metadata_json=None,
        experiment_name='experiment',
        model_name='run',
        model_load_path=None,
        model_resume_path=None,
        skip_save_progress_weights=False,
        skip_save_processed_input=False,
        output_directory='results',
        gpus=None,
        gpu_fraction=1.0,
        random_seed=42,
        debug=False,
        **kwargs
):
    """*full_train* defines the entire training scheme used by Ludwig's
    internals. Requires most of the parameters that are taken into the model.
    Builds a full ludwig model and initiates the training.
    :param model_definition: Model definition which defines the different
           parameters of the model, including the task, features as a yaml file
    :type model_definition: Dictionary
    :param model_definition_file: The file that specifies the model definition.
           It is a yaml file.
    :type model_definition_file: filepath (str)
    :param data_csv: The input data, $X, y$ which is used by Ludwig's core.
    :type data_csv: filepath (str)
    :param data_train_csv: Raw training data, only $X$ which is used by Ludwig's
           core.
    :type data_train_csv: filepath (str)
    :param data_validation_csv: Raw validation data, the hyperparameters are
           tuned on this dataset.
    :type data_validation_csv: filepath (str)
    :param data_test_csv: Raw test data, the model is evaluated on this data.
    :type data_test_csv: filepath (str)
    :param data_hdf5: If the dataset is in the hdf5 format, this is used instead
           of the csv file
    :type data_hdf5: filepath (str)
    :param data_train_hdf5: Train filepath in hdf5 format
    :type data_train_hdf5: filepath (str)
    :param data_validation_hdf5: Validation filepath in hdf5 format
    :type data_validation_hdf5: filepath (str)
    :param data_test_hdf5: Test data in the form of hdf5
    :type data_test_hdf5: filepath (str)
    :param metadata_json: If there is any metadata that the model requires, then
           this specifies the metadata.
    :type metadata_json: filepath (str)
    :param experiment_name: The name for the experiment
    :type experiment_name: Str
    :param model_name: Name of the model that is being used
    :type model_name: Str
    :param model_load_path: In the process of building the model,
           model_load_path is used by *build_model* to generate
    :type model_load_path: filepath (str)  TODO: Difference between model_load_path & model_resume_path
    :param model_resume_path: Resumes training of the model from the path
           specified.
    :type model_resume_path: filepath (str)
    :param skip_save_progress_weights: Skips saving the weights at the end of
           an epoch
    :type skip_save_progress_weights: Boolean
    :param skip_save_processed_input: Save the processed input after applying
           the *preprocess* function
    :type skip_save_processed_input: Boolean
    :param output_directory: The directory of the outputs or results of the
           model.
    :type output_directory: filepath (str)
    :param gpus: List of GPUs that are available for training/inference.
    :type gpus: List
    :param gpu_fraction: Fraction of each GPU to use
    :type gpu_fraction: Integer
    :param random_seed: Random seed to initialize weights
    :type random_seed: Integer
    :param debug: Whether the user intends to step through ludwig's internals
           for debugging purposes.
    :type debug: Boolean
    :returns: None
    """
    # set input features defaults
    if model_definition_file is not None:
        model_definition = merge_with_defaults(
            yaml.load(model_definition_file))
    else:
        model_definition = merge_with_defaults(model_definition)

    # setup directories and file names
    experiment_dir_name = None
    if model_resume_path is not None:
        if os.path.exists(model_resume_path):
            experiment_dir_name = model_resume_path
        else:
            logging.info(
                'Model resume path does not exists, '
                'starting training from scratch'
            )
            model_resume_path = None

    if model_resume_path is None:
        experiment_dir_name = get_experiment_dir_name(
            output_directory,
            experiment_name,
            model_name
        )

    description_fn, training_stats_fn, model_dir = get_file_names(
        experiment_dir_name
    )

    # save description
    description = get_experiment_description(
        model_definition,
        data_csv,
        data_train_csv,
        data_validation_csv,
        data_test_csv,
        data_hdf5,
        data_train_hdf5,
        data_validation_hdf5,
        data_test_hdf5,
        metadata_json,
        random_seed
    )
    save_json(description_fn, description)

    # print description
    logging.info('Experiment name: {}'.format(experiment_name))
    logging.info('Model name: {}'.format(model_name))
    logging.info('Output path: {}'.format(experiment_dir_name))
    logging.info('\n')
    for key, value in description.items():
        logging.info('{}: {}'.format(key, pformat(value, indent=4)))
    logging.info('\n')

    # preprocess
    training_set, validation_set, test_set, metadata = preprocess_for_training(
        model_definition,
        data_csv=data_csv,
        data_train_csv=data_train_csv,
        data_validation_csv=data_validation_csv,
        data_test_csv=data_test_csv,
        data_hdf5=data_hdf5,
        data_train_hdf5=data_train_hdf5,
        data_validation_hdf5=data_validation_hdf5,
        data_test_hdf5=data_test_hdf5,
        metadata_json=metadata_json,
        skip_save_processed_input=skip_save_processed_input,
        preprocessing_params=model_definition['preprocessing'],
        random_seed=random_seed
    )
    logging.info('Training set: {0}'.format(training_set.size))
    logging.info('Validation set: {0}'.format(validation_set.size))
    logging.info('Test set: {0}'.format(test_set.size))

    # update model definition with metadata properties
    update_model_definition_with_metadata(model_definition, metadata)

    # run the experiment
    model, result = train(
        training_set=training_set,
        validation_set=validation_set,
        test_set=test_set,
        model_definition=model_definition,
        save_path=model_dir,
        model_load_path=model_load_path,
        resume=model_resume_path is not None,
        skip_save_progress_weights=skip_save_progress_weights,
        gpus=gpus,
        gpu_fraction=gpu_fraction,
        random_seed=random_seed,
        debug=debug
    )
    train_trainset_stats, train_valisest_stats, train_testset_stats = result
    model.close_session()

    # save training and test statistics
    save_json(training_stats_fn, {'train': train_trainset_stats,
                                  'validation': train_valisest_stats,
                                  'test': train_testset_stats})

    # grab the results of the model with highest validation test performance
    validation_field = model_definition['training']['validation_field']
    validation_measure = model_definition['training']['validation_measure']
    validation_field_result = train_valisest_stats[validation_field]
    epoch_max_vali_measure, max_vali_measure = max(
        enumerate(validation_field_result[validation_measure]),
        key=lambda pair: pair[1]
    )
    max_vali_measure_epoch_test_measure = train_testset_stats[validation_field][
        validation_measure][epoch_max_vali_measure]

    # results of the model with highest validation test performance
    logging.info(
        'Best validation model epoch:'.format(epoch_max_vali_measure + 1)
    )
    logging.info('Best validation model {0} on validation set {1}: {2}'.format(
        validation_measure, validation_field, max_vali_measure
    ))
    logging.info('Best validation model {0} on test set {1}: {2}'.format(
        validation_measure, validation_field,
        max_vali_measure_epoch_test_measure
    ))
    logging.info('\nFinished: {0}_{1}'.format(experiment_name, model_name))
    logging.info('Saved to: {0}'.format(experiment_dir_name))


def train(
        training_set,
        validation_set,
        test_set,
        model_definition,
        save_path='model',
        model_load_path=None,
        resume=False,
        skip_save_progress_weights=False,
        gpus=None,
        gpu_fraction=1.0,
        random_seed=default_random_seed,
        debug=False
):
    """
    :param training_set: The training set for the model
    :type training_set: TODO: check
    :param validation_set: The validation set to train the hyperparameters
    :type validation_set: numpy array TODO: Check
    :param test_set: The test set.
    :type test_set: TODO: Check
    :param model_definition: The file that specifies the model definition. It is
          a yaml file.
    :type model_definition: filepath (str)
    :param save_path: The path to which the model is saved
    :type save_path: filepath (str)
    :param model_load_path: In the process of building the model,
           model_load_path is used by *build_model* to generate
    :type model_load_path: filepath (str)
    :param resume: Whether training is being resumed or it is beginning from
           scratch.
    :type resume: Boolean
    :param skip_save_progress_weights: Skips saving the weights at the end of an
           epoch
    :type skip_save_progress_weights: Boolean
    :param gpus: List of GPUs that are available for training/inference.
    :type gpus: List
    :param gpu_fraction: Fraction of each GPU to use
    :type gpu_fraction: Integer
    :param random_seed: Random seed to initialize weights
    :type random_seed: Integer
    :param debug: Whether the user intends to step through ludwig's internals
           for debugging purposes.
    :type debug: Boolean
    :raises: Exception
    """
    if model_load_path is not None:
        # Load model
        print_boxed('LOADING MODEL')
        logging.info('Loading model: {}\n'.format(model_load_path))
        model, _ = load_model_and_definition(model_load_path)
    else:
        # Build model
        print_boxed('BUILDING MODEL')
        model = Model(
            model_definition['input_features'],
            model_definition['output_features'],
            model_definition['combiner'],
            model_definition['training'],
            model_definition['preprocessing'],
            random_seed=random_seed,
            debug=debug
        )

    # Train model
    print_boxed('TRAINING')
    return model, model.train(
        training_set,
        validation_set=validation_set,
        test_set=test_set,
        save_path=save_path,
        resume=resume,
        skip_save_progress_weights=skip_save_progress_weights,
        gpus=gpus, gpu_fraction=gpu_fraction,
        random_seed=random_seed,
        **model_definition['training']
    )


def update_model_definition_with_metadata(model_definition, metadata):
    # populate input features fields depending on data
    # model_definition = merge_with_defaults(model_definition)
    for input_feature in model_definition['input_features']:
        feature = get_from_registry(
            input_feature['type'],
            input_type_registry
        )
        feature.populate_defaults(input_feature)
        feature.update_model_definition_with_metadata(
            input_feature,
            metadata[input_feature['name']],
            model_definition=model_definition
        )

    # populate output features fields depending on data
    for output_feature in model_definition['output_features']:
        feature = get_from_registry(
            output_feature['type'],
            output_type_registry
        )
        feature.populate_defaults(output_feature)
        feature.update_model_definition_with_metadata(
            output_feature,
            metadata[output_feature['name']]
        )

    for feature in (
            model_definition['input_features'] +
            model_definition['output_features']
    ):
        if 'preprocessing' in feature:
            feature['preprocessing'] = metadata[feature['name']][
                'preprocessing'
            ]


def get_experiment_dir_name(
        output_directory,
        experiment_name,
        model_name='run'
):
    results_dir = output_directory
    # create results dir if it doesn't exist
    if not os.path.isdir(results_dir):
        os.mkdir(results_dir)

    # create a base dir name
    base_dir_name = os.path.join(
        results_dir,
        experiment_name + ('_' if model_name else '') + model_name
    )

    # look for an unused suffix
    suffix = 0
    found_previous_results = os.path.isdir(
        '{base}_{suffix}'.format(base=base_dir_name, suffix=suffix)
    )

    while found_previous_results:
        suffix += 1
        found_previous_results = os.path.isdir(
            '{base}_{suffix}'.format(base=base_dir_name, suffix=suffix)
        )

    # found an unused suffix, build the basic dir name
    return '{base}_{suffix}'.format(base=base_dir_name, suffix=suffix)


def get_file_names(experiment_dir_name):
    if not os.path.exists(experiment_dir_name):
        os.mkdir(experiment_dir_name)

    description_fn = os.path.join(experiment_dir_name, 'description.json')
    training_stats_fn = os.path.join(
        experiment_dir_name, 'training_statistics.json')

    model_dir = os.path.join(experiment_dir_name, 'model')

    return description_fn, training_stats_fn, model_dir


def cli(sys_argv):
    parser = argparse.ArgumentParser(
        description='This script trains a model.',
        prog='ludwig train',
        usage='%(prog)s [options]'
    )

    # ----------------------------
    # Experiment naming parameters
    # ----------------------------
    parser.add_argument(
        '--output_directory',
        type=str,
        default='results',
        help='directory that contains the results'
    )
    parser.add_argument(
        '--experiment_name',
        type=str,
        default='experiment',
        help='experiment name'
    )
    parser.add_argument(
        '--model_name',
        type=str,
        default='run',
        help='name for the model'
    )

    # ---------------
    # Data parameters
    # ---------------
    parser.add_argument(
        '--data_csv',
        help='input data CSV file. '
             'If it has a split column, it will be used for splitting '
             '(0: train, 1: validation, 2: test), '
             'otherwise the dataset will be randomly split'
    )
    parser.add_argument('--data_train_csv', help='input train data CSV file')
    parser.add_argument(
        '--data_validation_csv',
        help='input validation data CSV file'
    )
    parser.add_argument('--data_test_csv', help='input test data CSV file')

    parser.add_argument(
        '--data_hdf5',
        help='input data HDF5 file. It is an intermediate preprocess version of'
             ' the input CSV created the first time a CSV file is used in the '
             'same directory with the same name and a hdf5 extension'
    )
    parser.add_argument(
        '--data_train_hdf5',
        help='input train data HDF5 file. It is an intermediate preprocess '
             'version of the input CSV created the first time a CSV file is '
             'used in the same directory with the same name and a hdf5 '
             'extension'
    )
    parser.add_argument(
        '--data_validation_hdf5',
        help='input validation data HDF5 file. It is an intermediate preprocess'
             ' version of the input CSV created the first time a CSV file is '
             'used in the same directory with the same name and a hdf5 '
             'extension'
    )
    parser.add_argument(
        '--data_test_hdf5',
        help='input test data HDF5 file. It is an intermediate preprocess '
             'version of the input CSV created the first time a CSV file is '
             'used in the same directory with the same name and a hdf5 '
             'extension'
    )

    parser.add_argument(
        '--metadata_json',
        help='input metadata JSON file. It is an intermediate preprocess file '
             'containing the mappings of the input CSV created the first time a'
             ' CSV file is used in the same directory with the same name and a '
             'json extension'
    )

    parser.add_argument(
        '-sspi',
        '--skip_save_processed_input',
        help='skips saving intermediate HDF5 and JSON files',
        action='store_true',
        default=False
    )

    # ----------------
    # Model parameters
    # ----------------
    model_definition = parser.add_mutually_exclusive_group(required=True)
    model_definition.add_argument(
        '-md',
        '--model_definition',
        type=yaml.load,
        help='model definition'
    )
    model_definition.add_argument(
        '-mdf',
        '--model_definition_file',
        help='YAML file describing the model. Ignores --model_hyperparameters'
    )

    parser.add_argument(
        '-mlp',
        '--model_load_path',
        help='path of a pretrained model to load as initialization'
    )
    parser.add_argument(
        '-mrp',
        '--model_resume_path',
        help='path of a the model directory to resume training of'
    )
    parser.add_argument(
        '-sspw',
        '--skip_save_progress_weights',
        help='does not save weights after each epoch. By default ludwig saves '
             'weights after each epoch for enabling resuming of training, but '
             'if the model is really big that can be time consuming and will '
             'save twice as much space, use this parameter to skip it.'
    )

    # ------------------
    # Runtime parameters
    # ------------------
    parser.add_argument(
        '-rs',
        '--random_seed',
        type=int,
        default=42,
        help='a random seed that is going to be used anywhere there is a call '
             'to a random number generator: data splitting, parameter '
             'initialization and training set shuffling'
    )
    parser.add_argument(
        '-g',
        '--gpus',
        nargs='+',
        type=int,
        default=None,
        help='list of gpus to use'
    )
    parser.add_argument(
        '-gf',
        '--gpu_fraction',
        type=float,
        default=1.0,
        help='fraction of gpu memory to initialize the process with'
    )
    parser.add_argument(
        '-dbg',
        '--debug',
        action='store_true',
        default=False, help='enables debugging mode'
    )
    parser.add_argument(
        '-l',
        '--logging_level',
        default='info',
        help='the level of logging to use',
        choices=['critical', 'error', 'warning', 'info', 'debug', 'notset']
    )

    args = parser.parse_args(sys_argv)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging_level_registry[args.logging_level],
        format='%(message)s'
    )

    print_ludwig('Train', LUDWIG_VERSION)

    full_train(**vars(args))


if __name__ == '__main__':
    cli(sys.argv[1:])