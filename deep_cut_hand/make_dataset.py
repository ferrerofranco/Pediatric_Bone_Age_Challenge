#!/usr/bin/python3
from multiprocessing import Process
from utilities import Console
import cv2
import fnmatch
import h5py
import multiprocessing
import numpy as np
import os
import pandas as pd
import platform
import sys

# Directory of dataset to use
TRAIN_DIR = "dataset_sample"
# TRAIN_DIR = "boneage-training-dataset"

# Use N images of dataset, If it is -1 using all dataset
CUT_DATASET = 1000

# For this problem the validation and test data provided by the concerned authority did not have labels,
# so the training data was split into train, test and validation sets
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
train_dir = os.path.join(__location__, "..", TRAIN_DIR)
img_file = ""


# Show a progress bar
def updateProgress(progress, tick="", total="", status="Loading..."):
    lineLength = 80
    barLength = 23
    if isinstance(progress, int):
        progress = float(progress)
    if progress < 0:
        progress = 0
        status = "Waiting...\r"
    if progress >= 1:
        progress = 1
        status = ""
    block = int(round(barLength * progress))
    line = str("\rImage: {0}/{1} [{2}] {3}% {4}").format(
        tick,
        total,
        str(("#" * block)) + str("." * (barLength - block)),
        round(progress * 100, 1),
        status,
    )
    emptyBlock = lineLength - len(line)
    emptyBlock = " " * emptyBlock if emptyBlock > 0 else ""
    sys.stdout.write(line + emptyBlock)
    sys.stdout.flush()
    if progress == 1:
        print()


# Show the images
def writeImage(path, image, force=False):
    if force:
        cv2.imwrite(os.path.join(__location__, path, img_file), image)


def saveDataSet(X_train, y_train):
    Console.info("Save dataset")
    with h5py.File("histogram-hand-dataset.hdf5", "w") as f:
        f.create_dataset("hist", data=X_train,)
        f.create_dataset("valid", data=y_train)
        f.flush()
        f.close()


def getHistogram(img):
    hist, _ = np.histogram(img, 256, [0, 256])

    cdf = hist.cumsum()
    cdf_normalized = cdf * hist.max() / cdf.max()

    return cdf_normalized


def loadDataSet(files=[]):
    global img_file
    X_train = []
    y_train = []

    total_file = len(files)
    for i in range(total_file):
        (img_file, lower, upper) = files[i]
        # Update the progress bar
        progress = float(i / total_file), (i + 1)
        updateProgress(progress[0], progress[1], total_file, img_file)

        # Get image's path
        img_path = os.path.join(train_dir, img_file)
        # Read a image
        img = cv2.imread(img_path, 0)
        img = histogramsLevelFix(img, lower, upper)

        X_train.append(getHistogram(img))
        y_train.append(1)

    return X_train, y_train


# Auto adjust levels colors
# We order the colors of the image with their frequency and
# obtain the accumulated one, then we obtain the colors that
# accumulate 2.5% and 99.4% of the frequency.
def histogramsLevelFix(img, min_color, max_color):
    # This function is only prepared for images in scale of gripes

    # To improve the preform we created a color palette with the new values
    colors_palette = []
    # Auxiliary calculation, avoid doing calculations within the 'for'
    dif_color = 255 / (max_color - min_color)
    for color in range(256):
        if color <= min_color:
            colors_palette.append(0)
        elif color >= max_color:
            colors_palette.append(255)
        else:
            colors_palette.append(int(round((color - min_color) * dif_color)))

    # We paint the image with the new color palette
    height, width = img.shape
    for y in range(0, height):
        for x in range(0, width):
            color = img[y, x]
            img[y, x] = colors_palette[color]

    writeImage("histograms_level", np.hstack([img]), True)  # show the images ===========

    return img


# list all the image files and randomly unravel them,
# in each case you take the first N from the unordered list
def getFiles():
    rta = []
    # Read csv
    df = pd.read_csv(os.path.join(train_dir, "histogram-dataset.csv"))

    # file names on train_dir
    files = os.listdir(train_dir)
    # filter image files
    files = [f for f in files if fnmatch.fnmatch(f, "*.png")]
    # Sort randomly
    np.random.shuffle(files)

    for file_name in files:
        # Cut list of file
        if CUT_DATASET <= 0 or len(rta) < CUT_DATASET:
            # print(file_name)
            # Get row with id equil image's name
            csv_row = df[df.id == int(file_name[:-4])]
            # Get lower color
            lower = csv_row.lower.tolist()
            # Get upper color
            upper = csv_row.upper.tolist()
            if (lower and upper) and (
                not (lower[0] != lower[0] and upper[0] != upper[0])
            ):
                rta.append((file_name, lower[0], upper[0]))
            else:
                Console.log("Not data for", file_name)

    return rta


def openDataSet():
    with h5py.File("histogram-hand-dataset.hdf5", "r+") as f:
        hist = f['hist'][()]
        valid = f['valid'][()]
        print(len(hist[0]), len(valid))
        # f.flush()
        f.close()


# Usado en caso de usar multiples core
output = multiprocessing.Queue()


def mpStart(files, output):
    output.put(loadDataSet(files))


if __name__ == "__main__":
    files = getFiles()
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
            processes.append(Process(target=mpStart, args=(lot_img, output)))

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
            updateProgress(1, total_file, total_file, img_file)

            saveDataSet(X_train, y_train)
    else:
        Console.info("No podemos dividir la cargan en distintos procesadores")
        exit(0)

    openDataSet()
