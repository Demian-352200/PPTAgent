import os

import numpy as np
import pytorch_fid.fid_score as fid
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode

from utils import pjoin

fid.tqdm = lambda x: x

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


# < 150效果比较好
def fid_score(img_dir: str, batch_size: int = None):
    img_files = [f for f in os.listdir(img_dir)]
    num_images = len(img_files)
    fid_scores = np.zeros((num_images, num_images))
    os.makedirs(".temp_1")
    os.makedirs(".temp_2")
    for i in range(num_images):
        for j in range(i + 1, num_images):
            img_i_path = pjoin(img_dir, img_files[i])
            img_j_path = pjoin(img_dir, img_files[j])
            os.rename(img_i_path, pjoin(".temp_1", img_files[i]))
            os.rename(img_j_path, pjoin(".temp_2", img_files[j]))
            fid_value = fid.calculate_fid_given_paths(
                [".temp_1", ".temp_2"],
                batch_size=1,
                device="cuda" if torch.cuda.is_available() else "cpu",
                dims=2048,
            )
            fid_scores[i, j] = fid_value
            fid_scores[j, i] = fid_value

            if fid_value < 150:
                print(f"{img_files[i]} - {img_files[j]}: {fid_value}")
            os.rename(pjoin(".temp_1", img_files[i]), img_i_path)
            os.rename(pjoin(".temp_2", img_files[j]), img_j_path)

    os.system("rm -rf .temp_1")
    os.system("rm -rf .temp_2")
    print(fid_scores)


def build_transform(input_size):
    MEAN, STD = IMAGENET_MEAN, IMAGENET_STD
    transform = T.Compose(
        [
            T.Lambda(lambda img: img.convert("RGB") if img.mode != "RGB" else img),
            T.Resize(
                (input_size, input_size),
                interpolation=InterpolationMode.BICUBIC,
            ),
            T.ToTensor(),
            T.Normalize(mean=MEAN, std=STD),
        ]
    )
    return transform


def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float("inf")
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio


def dynamic_preprocess(
    image, min_num=1, max_num=6, image_size=448, use_thumbnail=False
):
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    # calculate the existing image aspect ratio
    target_ratios = set(
        (i, j)
        for n in range(min_num, max_num + 1)
        for i in range(1, n + 1)
        for j in range(1, n + 1)
        if i * j <= max_num and i * j >= min_num
    )
    target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

    # find the closest aspect ratio to the target
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size
    )

    # calculate the target width and height
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    # resize the image
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size,
        )
        # split the image
        split_img = resized_img.crop(box)
        processed_images.append(split_img)
    assert len(processed_images) == blocks
    if use_thumbnail and len(processed_images) != 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return target_aspect_ratio, processed_images


def load_image(image_file, input_size=448, max_num=16):
    image = Image.open(image_file).convert("RGB")
    transform = build_transform(input_size=input_size)
    target_aspect_ratio, images = dynamic_preprocess(
        image, image_size=input_size, use_thumbnail=True, max_num=max_num
    )
    pixel_values = [transform(image) for image in images]
    pixel_values = torch.stack(pixel_values)
    return target_aspect_ratio, pixel_values
