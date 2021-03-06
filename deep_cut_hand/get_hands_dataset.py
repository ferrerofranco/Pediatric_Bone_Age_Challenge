#!/usr/bin/python3
from multiprocessing import Process
from utilities import Console, updateProgress, getHistogram
from makeHandsFromCSV import makeHandsHuman
import cv2
import fnmatch
import h5py
import multiprocessing
import numpy as np
import os
import platform

# Use N images of dataset, If it is -1 using all dataset
CUT_DATASET = 1000
# Get lower and upper for csv and make hands img
MAKE_HANDS_FROM_HUMAN = True

# For this problem the validation and test data provided by the concerned authority did not have labels,
# so the training data was split into train, test and validation sets
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


def saveDataSet(X_train, y_train):
    Console.info("Save dataset")
    file_path = os.path.join(
        __location__,
        "dataset_hands",
        "histogram-hand-dataset.hdf5"
    )
    with h5py.File(file_path, "w") as f:
        f.create_dataset("hist", data=X_train)
        f.create_dataset("valid", data=y_train)
        f.flush()
        f.close()


def loadDataSet(path, files=[], hands_valid=1):
    X_train = []
    y_train = []

    total_file = len(files)
    for i in range(total_file):
        img_file = files[i]
        # Update the progress bar
        progress = float(i / total_file), (i + 1)
        updateProgress(progress[0], progress[1], total_file, img_file)

        # Get image's path
        img_path = os.path.join(path, img_file)
        # Read a image
        img = cv2.imread(img_path, 0)

        X_train.append(getHistogram(img))
        y_train.append(hands_valid)

    return X_train, y_train


# list all the image files and randomly unravel them,
# in each case you take the first N from the unordered list
def getFiles(path_input):
    Console.info("Reading on", path_input)
    path = os.path.join(__location__)
    for p in path_input:
        path = os.path.join(path, p)

    rta = []
    # file names on train_dir
    files = os.listdir(path)
    # filter image files
    files = [f for f in files if fnmatch.fnmatch(f, "*.png")]

    for file_name in files:
        # Cut list of file
        if CUT_DATASET <= 0 or len(rta) < CUT_DATASET:
            rta.append(file_name)

    return rta


def openDataSet():
    file_path = os.path.join(
        __location__,
        "dataset_hands",
        "histogram-hand-dataset.hdf5"
    )
    with h5py.File(file_path, "r+") as f:
        hist = f["hist"][()]
        valid = f["valid"][()]
        f.close()

    return hist, valid


# Usado en caso de usar multiples core
output = multiprocessing.Queue()


def mpStart(path, files, hands_valid, output, progress_num):
    output.put(loadDataSet(path, files, hands_valid))


def progressFiles(path_input, files, hands_valid):
    path = os.path.join(__location__)
    for p in path_input:
        path = os.path.join(path, p)

    total_file = len(files)
    Console.info("Image total:", total_file)

    num_processes = multiprocessing.cpu_count()
    if platform.system() == "Linux" and num_processes > 1:
        processes = []

        lot_size = int(total_file / num_processes)

        for x in range(1, num_processes + 1):
            if x < num_processes:
                lot_img = files[(x - 1) * lot_size: ((x - 1) * lot_size) + lot_size]
            else:
                lot_img = files[(x - 1) * lot_size:]
            processes.append(
                Process(target=mpStart, args=(path, lot_img, hands_valid, output, x))
            )

        if len(processes) > 0:
            Console.info("Get histogram of the images...")
            for p in processes:
                p.start()

            result = []
            for x in range(num_processes):
                result.append(output.get(True))

            for p in processes:
                p.join()

            X_train = []
            y_train = []
            for mp_X_train, mp_y_train in result:
                X_train = X_train + mp_X_train
                y_train = y_train + mp_y_train
            updateProgress(1, total_file, total_file, "")

            return X_train, y_train
    else:
        Console.info("No podemos dividir la cargan en distintos procesadores")
        exit(0)


if __name__ == "__main__":
    if MAKE_HANDS_FROM_HUMAN:
        makeHandsHuman()

    TRAIN_DIR = ["dataset_hands", "hands"]
    files = getFiles(TRAIN_DIR)
    (X_train, y_train) = progressFiles(TRAIN_DIR, files, hands_valid=1)

    TRAIN_DIR = ["dataset_hands", "not_hands"]
    files = getFiles(TRAIN_DIR)
    (X2_train, y2_train) = progressFiles(TRAIN_DIR, files, hands_valid=0)

    X_train = X_train + X2_train
    y_train = y_train + y2_train

    # Sort randomly
    random_id = np.random.choice(len(X_train), size=len(y_train), replace=False)
    X_train = np.asarray(X_train)[random_id]
    y_train = np.asarray(y_train)[random_id]

    saveDataSet(X_train, y_train)

    hist, valid = openDataSet()
    Console.log("Dataset", len(hist[0]), len(valid))
