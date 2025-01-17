from numpy import equal
import pandas as pd
import torch
import torch.nn.functional as F
from torch.nn.modules.dropout import Dropout
from torch.optim import SGD
from torch.utils.data import DataLoader
from torch.nn import Linear, CrossEntropyLoss, Sequential
from torch.utils.data import sampler
from torch.utils.data.sampler import WeightedRandomSampler

import torchvision.transforms as transforms
from torchvision import models
import albumentations as A
from albumentations.pytorch import ToTensorV2

from iris.data import LandMarkDataset
from iris.models.baseline import BaseLine
from iris.train_loop import TrainLoop


def main(
    img_dir: str,
    img_metadata: pd.DataFrame,
    train_trans: transforms.Compose,
    dev_trans: transforms.Compose,
    batch_size: int,
    model: torch.nn.Module,
    out_features: int,
    optimizer_params: dict,
    lr_scheduler_params: dict,
    num_epochs: int,
    save_models: str,
    device:str,
    features_weights: list = None,
):
    sampler = (
        WeightedRandomSampler(features_weights, img_metadata[0].shape[0])
        if features_weights is not None
        else None
    )

    # Creates dataset and dataloaders
    train_ds = LandMarkDataset(img_dir, img_metadata[0], train_trans)
    test_ds = LandMarkDataset(img_dir, img_metadata[1], dev_trans)
    train_dl = DataLoader(train_ds, batch_size=batch_size, sampler=sampler)
    test_dl = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    dataloaders = {"train": train_dl, "val": test_dl}
    
    # Define optmizer    
    optimizer = SGD(model.parameters(), **optimizer_params)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, **lr_scheduler_params)

    # Train-val step
    train_loop = TrainLoop(
        num_clases=out_features,
        device=device
    )
    
    train_loop.train_val(
        num_epochs=num_epochs, 
        dataloaders=dataloaders, 
        model=model, 
        criterion=CrossEntropyLoss(), 
        optimizer=optimizer, 
        scheduler=lr_scheduler,
        save_models=save_models 
    )


if __name__ == "__main__":
    features_weights = None
    equal_w = True
    require_grad = True
    out_features = 20
    
    img_metadata = pd.read_csv("img_metadata_train_dev.csv")
    train_img_metadata = img_metadata[img_metadata.iloc[:, 1] != 0]
    test_img_metadata = img_metadata[img_metadata.iloc[:, 1] == 0]
    
    
    if features_weights is not None:
        if equal_w:
            features_weights = [1/out_features] * test_img_metadata.shape[0]
        else:
            features_weights = img_metadata[img_metadata.iloc[:, 1] == 0].iloc[:, 4]

    train_trans = A.Compose(
            [
                A.Resize(224, 224),
                A.CoarseDropout(always_apply=False, p=0.3, max_holes=5, max_height=40, max_width=40, min_holes=1, min_height=8, min_width=8),
                A.CenterCrop(height=224, width=224, p=0.3),
                A.RandomBrightnessContrast(p=0.3),
                A.Flip(always_apply=False, p=0.3),
                A.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
                ToTensorV2(),
            ])
    
    val_trans = A.Compose(
            [
                A.Resize(224, 224),
                A.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
                ToTensorV2(),
            ])

    # define model and move model to the right device
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = models.densenet121(pretrained=True)
    if not require_grad:
        for param in model.parameters():
                param.requires_grad = False
    
    model.classifier = Sequential(
        Linear(model.classifier.in_features, out_features)
    )
    model = model.to(device)

    main(
        img_dir="data/train/",
        img_metadata=(train_img_metadata, test_img_metadata),
        train_trans=train_trans,
        dev_trans=val_trans,
        batch_size=64,
        model=model,
        out_features=out_features,
        optimizer_params={"lr": 0.001, "momentum": 0.9},
        lr_scheduler_params={"gamma": 0.1, "step_size": 500, "verbose": False},
        num_epochs=25,
        save_models="saved_models",
        device=device,
        features_weights=features_weights,
    )
