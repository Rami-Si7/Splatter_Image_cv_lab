import glob
import hydra
import os
import wandb

import numpy as np
import torch
import math
from torch.utils.data import DataLoader
from torch.utils.data import Sampler
from lightning.fabric import Fabric
from ema_pytorch import EMA
from omegaconf import DictConfig, OmegaConf
from utils.general_utils import safe_state
from utils.loss_utils import l1_loss, l2_loss
import lpips as lpips_lib
from eval import evaluate_dataset
from gaussian_renderer import render_predicted
from scene.gaussian_predictor import GaussianSplatPredictor
from datasets.dataset_factory import get_dataset
from torch.utils.data import DataLoader, SequentialSampler
from torch.utils.data import Dataset
class TargetReconstructionDataset(Dataset):
    
    """
    Dataset class for loading target reconstructions from folders.
    Each folder contains one sample's reconstruction.
    """
    def __init__(self, root_dir):
        self.root_dir = root_dir
        # Sort folder names to ensure order
        self.folders = sorted([folder for folder in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, folder))])

    def __len__(self):
        return len(self.folders)

    def __getitem__(self, idx):
        folder_name = self.folders[idx]
        reconstruction_path = os.path.join(self.root_dir, folder_name, 'reconstruction.pt')
        
        if os.path.exists(reconstruction_path):
            reconstruction_data = torch.load(reconstruction_path)
        else:
            print(f"Warning: No reconstruction.pt found in {folder_name}")
            reconstruction_data = None  # Handle missing data if necessary

        return folder_name, reconstruction_data


def get_reconstruction_dataloader(target_dir, batch_size, num_workers=0):
    """
    Returns a DataLoader for loading target reconstructions in batches.
    """
    target_dataset = TargetReconstructionDataset(target_dir)
    target_dataloader = DataLoader(target_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    return target_dataloader


def normalize_channels_min_max(tensor):
    """
    Normalize each channel in the tensor individually based on min and max values.
    Handles 2D, 3D, and 4D tensors.

    :param tensor: Tensor of shape [B, C, H, W], [B, N, C], or [N, C]
    :return: Normalized tensor
    """
    if tensor.dim() == 4:  # Case for [B, C, H, W] format
        min_vals = tensor.amin(dim=[2, 3], keepdim=True)  # Min over H and W dimensions
        max_vals = tensor.amax(dim=[2, 3], keepdim=True)  # Max over H and W dimensions
    elif tensor.dim() == 3:  # Case for [B, N, C] format
        min_vals = tensor.amin(dim=1, keepdim=True)  # Min over N dimension
        max_vals = tensor.amax(dim=1, keepdim=True)  # Max over N dimension
    elif tensor.dim() == 2:  # Case for [N, C] format
        min_vals = tensor.amin(dim=0, keepdim=True)  # Min over N dimension
        max_vals = tensor.amax(dim=0, keepdim=True)  # Max over N dimension
    elif tensor.dim() == 5:  # Assuming the shape is [B, 1, N, 1, C] -> treat [N, C] as [H, W]
        tensor = tensor.squeeze(1).squeeze(2)  # Remove singleton dimensions
        min_vals = tensor.amin(dim=[1, 2], keepdim=True)
        max_vals = tensor.amax(dim=[1, 2], keepdim=True)
    else:
        raise ValueError(f"Unsupported tensor shape: {tensor.shape}")

    # Normalize each channel individually
    normalized = (tensor - min_vals) / (max_vals - min_vals + 1e-8)
    
    return normalized


def custom_loss_fn_batched(target_reconstructions, gaussian_splats):
    total_loss = 0.0

    # Ensure the shapes match by squeezing unnecessary dimensions
    target_reconstructions['xyz'] = target_reconstructions['xyz'].squeeze(dim=1)
    target_reconstructions['scaling'] = target_reconstructions['scaling'].squeeze(dim=1)
    target_reconstructions['features_dc'] = target_reconstructions['features_dc'].squeeze(dim=1)
    target_reconstructions['features_rest'] = target_reconstructions['features_rest'].squeeze(dim=1)
    target_reconstructions['opacity'] = target_reconstructions['opacity'].squeeze(dim=1)

    # 'xyz' components comparison
    if 'xyz' in target_reconstructions and 'xyz' in gaussian_splats:
        target_xyz = normalize_channels_min_max(target_reconstructions['xyz'])  # Shape: [Batch_size, C, H, W]
        current_xyz = normalize_channels_min_max(gaussian_splats['xyz'])  # Shape: [Batch_size, C, H, W]
        target_opacity = target_reconstructions['opacity']  # Shape: [Batch_size, C, H, W]

        # Batched difference and weighted sum over the entire batch
        diff_xyz = current_xyz.sub(target_xyz).pow(2)  # Shape: [Batch_size, C, H, W]
        weighted_diff_xyz = diff_xyz.mul(target_opacity)  # Shape: [Batch_size, C, H, W]
        total_loss += torch.mean(weighted_diff_xyz)
    if 'rotation' in target_reconstructions and 'rotation' in gaussian_splats:
        target_rotation = normalize_channels_min_max(target_reconstructions['rotation'])  # Shape: [Batch_size, C, H, W]
        current_rotation = normalize_channels_min_max(gaussian_splats['rotation'])  # Shape: [Batch_size, C, H, W]
        target_opacity = target_reconstructions['opacity']  # Shape: [Batch_size, C, H, W]

        # Batched difference and weighted sum over the entire batch
        diff_rotation = current_rotation.sub(target_rotation).pow(2)  # Shape: [Batch_size, C, H, W]
        weighted_diff_xyz = diff_xyz.mul(target_opacity)  # Shape: [Batch_size, C, H, W]
        total_loss += torch.mean(weighted_diff_xyz)

    # 'scaling' components comparison
    if 'scaling' in target_reconstructions and 'scaling' in gaussian_splats:
        target_scaling = normalize_channels_min_max(target_reconstructions['scaling'])
        current_scaling = normalize_channels_min_max(gaussian_splats['scaling'])
        target_opacity = target_reconstructions['opacity']

        diff_scaling = current_scaling.sub(target_scaling).pow(2)
        weighted_diff_scaling = diff_scaling.mul(target_opacity)
        total_loss += torch.mean(weighted_diff_scaling)

    # 'features_dc' components comparison
    if 'features_dc' in target_reconstructions and 'features_dc' in gaussian_splats:
        target_features_dc = normalize_channels_min_max(target_reconstructions['features_dc'])
        current_features_dc = normalize_channels_min_max(gaussian_splats['features_dc'])
        target_opacity = target_reconstructions['opacity']

        diff_features_dc = current_features_dc.sub(target_features_dc).mean(dim=-1, keepdim=True).squeeze(-1).pow(2)
        # print(f"Shape of diff_features_dc: {diff_features_dc.shape}")

        weighted_diff_features_dc = diff_features_dc.mul(target_opacity)
        total_loss += torch.mean(weighted_diff_features_dc)

    # 'features_rest' components comparison
    if 'features_rest' in target_reconstructions and 'features_rest' in gaussian_splats:
        target_features_rest = normalize_channels_min_max(target_reconstructions['features_rest'])
        current_features_rest = normalize_channels_min_max(gaussian_splats['features_rest'])
        target_opacity = target_reconstructions['opacity']

        # Batched difference, taking the mean over H and W dimensions
        mean_features_rest = torch.mean(current_features_rest.sub(target_features_rest).pow(2), dim=[2, 3], keepdim=True).squeeze(-1)
        # print(f"Shape of mean_features_rest: {mean_features_rest.shape}")

        weighted_diff_features_rest = mean_features_rest.mul(target_opacity)
        total_loss += torch.mean(weighted_diff_features_rest)

    # 'opacity' components comparison
    if 'opacity' in target_reconstructions and 'opacity' in gaussian_splats:
        total_loss += torch.nn.functional.mse_loss(
            gaussian_splats['opacity'], target_reconstructions['opacity']
        )

    return total_loss


@hydra.main(version_base=None, config_path='configs', config_name="default_config")
def main(cfg: DictConfig):

  
    torch.set_float32_matmul_precision('high')
    if cfg.general.mixed_precision:
        fabric = Fabric(accelerator="cuda", devices=cfg.general.num_devices, strategy="ddp",
                        precision="16-mixed")
    else:
        fabric = Fabric(accelerator="cuda", devices=cfg.general.num_devices, strategy="ddp")
    fabric.launch()

    if fabric.is_global_zero:
        vis_dir = os.getcwd()

        dict_cfg = OmegaConf.to_container(
            cfg, resolve=True, throw_on_missing=True
        )

        if os.path.isdir(os.path.join(vis_dir, "wandb")):
            run_name_path = glob.glob(os.path.join(vis_dir, "wandb", "latest-run", "run-*"))[0]
            print("Got run name path {}".format(run_name_path))
            run_id = os.path.basename(run_name_path).split("run-")[1].split(".wandb")[0]
            print("Resuming run with id {}".format(run_id))
            wandb_run = wandb.init(project=cfg.wandb.project, resume=True,
                            id = run_id, config=dict_cfg)

        else:
            wandb_run = wandb.init(project=cfg.wandb.project, reinit=True,
                            config=dict_cfg)

    first_iter = 0
    device = safe_state(cfg)

    gaussian_predictor = GaussianSplatPredictor(cfg)
    gaussian_predictor = gaussian_predictor.to(memory_format=torch.channels_last)

    l = []
    if cfg.model.network_with_offset:
        l.append({'params': gaussian_predictor.network_with_offset.parameters(), 
         'lr': cfg.opt.base_lr})
    if cfg.model.network_without_offset:
        l.append({'params': gaussian_predictor.network_wo_offset.parameters(), 
         'lr': cfg.opt.base_lr})
    # optimizer = torch.optim.Adam(l, lr=0.0, eps=1e-15, 
    #                              betas=cfg.opt.betas)
    # Initialize the optimizer with weight decay (L2 regularization)
    optimizer = torch.optim.Adam(l, lr=0.0, eps=1e-15, betas=cfg.opt.betas)  # Set weight_decay to a small value like 1e-5


    # Resuming training
    if fabric.is_global_zero:
        if os.path.isfile(os.path.join(vis_dir, "model_latest.pth")):
            print('Loading an existing model from ', os.path.join(vis_dir, "model_latest.pth"))
            checkpoint = torch.load(os.path.join(vis_dir, "model_latest.pth"),
                                    map_location=device) 
            try:
                gaussian_predictor.load_state_dict(checkpoint["model_state_dict"])
            except RuntimeError:
                gaussian_predictor.load_state_dict(checkpoint["model_state_dict"],
                                                strict=False)
                print("Warning, model mismatch - was this expected?")
            first_iter = checkpoint["iteration"]
            best_PSNR = checkpoint["best_PSNR"] 
            print('Loaded model')
        # Resuming from checkpoint
        elif cfg.opt.pretrained_ckpt is not None:
            pretrained_ckpt_dir = os.path.join(cfg.opt.pretrained_ckpt, "model_latest.pth")
            checkpoint = torch.load(pretrained_ckpt_dir,
                                    map_location=device) 
            try:
                gaussian_predictor.load_state_dict(checkpoint["model_state_dict"])
            except RuntimeError:
                gaussian_predictor.load_state_dict(checkpoint["model_state_dict"],
                                                strict=False)
            best_PSNR = checkpoint["best_PSNR"] 
            print('Loaded model from a pretrained checkpoint')
        else:
            best_PSNR = 0.0

    if cfg.opt.ema.use and fabric.is_global_zero:
        ema = EMA(gaussian_predictor, 
                  beta=cfg.opt.ema.beta,
                  update_every=cfg.opt.ema.update_every,
                  update_after_step=cfg.opt.ema.update_after_step)
        ema = fabric.to_device(ema)

    if cfg.opt.loss == "l2":
        loss_fn = l2_loss
    elif cfg.opt.loss == "l1":
        loss_fn = l1_loss

    if cfg.opt.lambda_lpips != 0:
        lpips_fn = fabric.to_device(lpips_lib.LPIPS(net='vgg'))
    lambda_lpips = cfg.opt.lambda_lpips
    lambda_l12 = 1.0 - lambda_lpips

    bg_color = [1, 1, 1] if cfg.data.white_background else [0, 0, 0]
    background = torch.tensor(bg_color, dtype=torch.float32)
    background = fabric.to_device(background)

    if cfg.data.category in ["nmr", "objaverse"]:
        num_workers = 12
        persistent_workers = True
    else:
        num_workers = 0
        persistent_workers = False

    dataset = get_dataset(cfg, "train")

    # please set here you GT target splatter images
    target_dataset = TargetReconstructionDataset(root_dir="/content/SI_target")

    main_sampler = SequentialSampler(dataset)

    target_sampler = SequentialSampler(target_dataset)

    dataloader = DataLoader(dataset, 
                            batch_size=cfg.opt.batch_size,
                            sampler=main_sampler,  # Use sorted sampler
                            num_workers=num_workers,
                            persistent_workers=persistent_workers)

    target_dataloader = DataLoader(target_dataset, 
                                  batch_size=cfg.opt.batch_size,
                                  sampler=target_sampler,  # Use sorted sampler
                                  num_workers=num_workers)

    val_dataset = get_dataset(cfg, "val")
    val_dataloader = DataLoader(val_dataset, 
                                batch_size=1,
                                shuffle=False,
                                num_workers=1,
                                persistent_workers=True,
                                pin_memory=True)

    test_dataset = get_dataset(cfg, "vis")
    test_dataloader = DataLoader(test_dataset, 
                                 batch_size=1,
                                 shuffle=True)
    
    # distribute model and training dataset
    gaussian_predictor, optimizer = fabric.setup(
        gaussian_predictor, optimizer
    )
    dataloader = fabric.setup_dataloaders(dataloader)
    
    gaussian_predictor.train()

    custom_lambda = 0


    print("Beginning training")
    first_iter += 1
    iteration = first_iter
    # target_dir = "/content/SI_target"

    for num_epoch in range((cfg.opt.iterations + 1 - first_iter)// len(dataloader) + 1):
        dataloader.sampler.set_epoch(num_epoch)        

        for data, target_batch in zip(dataloader, target_dataloader):
            iteration += 1
            target_names, target_reconstructions = target_batch

 


            print("starting iteration {} on process {}".format(iteration, fabric.global_rank))

            # =============== Prepare input ================
            rot_transform_quats = data["source_cv2wT_quat"][:, :cfg.data.input_images]

            if cfg.data.category == "hydrants" or cfg.data.category == "teddybears":
                focals_pixels_pred = data["focals_pixels"][:, :cfg.data.input_images, ...]
                input_images = torch.cat([data["gt_images"][:, :cfg.data.input_images, ...],
                                data["origin_distances"][:, :cfg.data.input_images, ...]],
                                dim=2)
            else:
                focals_pixels_pred = None
                input_images = data["gt_images"][:, :cfg.data.input_images, ...]

            gaussian_splats = gaussian_predictor(input_images,
                                                data["view_to_world_transforms"][:, :cfg.data.input_images, ...],
                                                rot_transform_quats,
                                                focals_pixels_pred)


            if cfg.data.category == "hydrants" or cfg.data.category == "teddybears":
                # regularize very big gaussians
                if len(torch.where(gaussian_splats["scaling"] > 20)[0]) > 0:
                    big_gaussian_reg_loss = torch.mean(
                        gaussian_splats["scaling"][torch.where(gaussian_splats["scaling"] > 20)] * 0.1)
                    print('Regularising {} big Gaussians on iteration {}'.format(
                        len(torch.where(gaussian_splats["scaling"] > 20)[0]), iteration))
                else:
                    big_gaussian_reg_loss = 0.0
                # regularize very small Gaussians
                if len(torch.where(gaussian_splats["scaling"] < 1e-5)[0]) > 0:
                    small_gaussian_reg_loss = torch.mean(
                        -torch.log(gaussian_splats["scaling"][torch.where(gaussian_splats["scaling"] < 1e-5)]) * 0.1)
                    print('Regularising {} small Gaussians on iteration {}'.format(
                        len(torch.where(gaussian_splats["scaling"] < 1e-5)[0]), iteration))
                else:
                    small_gaussian_reg_loss = 0.0
            # Render
            l12_loss_sum = 0.0
            lpips_loss_sum = 0.0
            rendered_images = []
            gt_images = []
            for b_idx in range(data["gt_images"].shape[0]):
                # image at index 0 is training, remaining images are targets
                # Rendering is done sequentially because gaussian rasterization code
                # does not support batching
                gaussian_splat_batch = {k: v[b_idx].contiguous() for k, v in gaussian_splats.items()}
                for r_idx in range(cfg.data.input_images, data["gt_images"].shape[1]):
                    if "focals_pixels" in data.keys():
                        focals_pixels_render = data["focals_pixels"][b_idx, r_idx].cpu()
                    else:
                        focals_pixels_render = None
                    image = render_predicted(gaussian_splat_batch, 
                                        data["world_view_transforms"][b_idx, r_idx],
                                        data["full_proj_transforms"][b_idx, r_idx],
                                        data["camera_centers"][b_idx, r_idx],
                                        background,
                                        cfg,
                                        focals_pixels=focals_pixels_render)["render"]
                    # Put in a list for a later loss computation
                    rendered_images.append(image)
                    gt_image = data["gt_images"][b_idx, r_idx]
                    gt_images.append(gt_image)
            rendered_images = torch.stack(rendered_images, dim=0)
            gt_images = torch.stack(gt_images, dim=0)
            # Loss computation
            l12_loss_sum = loss_fn(rendered_images, gt_images) 
            if cfg.opt.lambda_lpips != 0:
                lpips_loss_sum = torch.mean(
                    lpips_fn(rendered_images * 2 - 1, gt_images * 2 - 1),
                    )
            if 3000 <= iteration < 4000:
              custom_lambda = 0.03
            elif 4000 <= iteration < 7000:
              custom_lambda = 0.05
            elif 7000 <= iteration < 10000:
              custom_lambda = 0.08                                       
            elif 10000 <= iteration:
              custom_lambda = 0.1
            base_loss = l12_loss_sum * lambda_l12 + lpips_loss_sum * lambda_lpips
            custom_loss = custom_lambda * custom_loss_fn_batched(target_reconstructions, gaussian_splats)
            total_loss = base_loss + custom_loss
            if cfg.data.category == "hydrants" or cfg.data.category == "teddybears":
                total_loss = total_loss + big_gaussian_reg_loss + small_gaussian_reg_loss

            assert not total_loss.isnan(), "Found NaN loss!"
            print("finished forward {} on process {}".format(iteration, fabric.global_rank))
            fabric.backward(total_loss)

            # ============ Optimization ===============
            optimizer.step()
            optimizer.zero_grad()
            print("finished opt {} on process {}".format(iteration, fabric.global_rank))

            if cfg.opt.ema.use and fabric.is_global_zero:
                ema.update()

            print("finished iteration {} on process {}".format(iteration, fabric.global_rank))

            gaussian_predictor.eval()

            # ========= Logging =============
            with torch.no_grad():

                if iteration % cfg.logging.loss_log == 0 and fabric.is_global_zero:
                    wandb.log({
                        "training_loss": np.log10(total_loss.item() + 1e-8), 
                        "base_loss": np.log10(base_loss.item() + 1e-8), 
                        "custom_loss": np.log10(custom_loss.cpu().item() + 1e-8),  # Move to CPU and then get item
                        "custom_lambda": custom_lambda
                    }, step=iteration)

                    if cfg.opt.lambda_lpips != 0:
                        wandb.log({"training_l12_loss": np.log10(l12_loss_sum.item() + 1e-8)}, step=iteration)
                        wandb.log({"training_lpips_loss": np.log10(lpips_loss_sum.item() + 1e-8)}, step=iteration)
                    if cfg.data.category == "hydrants" or cfg.data.category == "teddybears":
                        if type(big_gaussian_reg_loss) == float:
                            brl_for_log = big_gaussian_reg_loss
                        else:
                            brl_for_log = big_gaussian_reg_loss.item()
                        if type(small_gaussian_reg_loss) == float:
                            srl_for_log = small_gaussian_reg_loss
                        else:
                            srl_for_log = small_gaussian_reg_loss.item()
                        wandb.log({"reg_loss_big": np.log10(brl_for_log + 1e-8)}, step=iteration)
                        wandb.log({"reg_loss_small": np.log10(srl_for_log + 1e-8)}, step=iteration)

                if (iteration % cfg.logging.render_log == 0 or iteration == 1) and fabric.is_global_zero:
                    wandb.log({"render": wandb.Image(image.clamp(0.0, 1.0).permute(1, 2, 0).detach().cpu().numpy())}, step=iteration)
                    wandb.log({"gt": wandb.Image(gt_image.permute(1, 2, 0).detach().cpu().numpy())}, step=iteration)
                if (iteration % cfg.logging.loop_log == 0 or iteration == 1) and fabric.is_global_zero:
                    # torch.cuda.empty_cache()
                    try:
                        vis_data = next(test_iterator)
                    except UnboundLocalError:
                        test_iterator = iter(test_dataloader)
                        vis_data = next(test_iterator)
                    except StopIteration or UnboundLocalError:
                        test_iterator = iter(test_dataloader)
                        vis_data = next(test_iterator)

                    vis_data = {k: fabric.to_device(v) for k, v in vis_data.items()}

                    rot_transform_quats = vis_data["source_cv2wT_quat"][:, :cfg.data.input_images]

                    if cfg.data.category == "hydrants" or cfg.data.category == "teddybears":
                        focals_pixels_pred = vis_data["focals_pixels"][:, :cfg.data.input_images, ...]
                        input_images = torch.cat([vis_data["gt_images"][:, :cfg.data.input_images, ...],
                                                vis_data["origin_distances"][:, :cfg.data.input_images, ...]],
                                                dim=2)
                    else:
                        focals_pixels_pred = None
                        input_images = vis_data["gt_images"][:, :cfg.data.input_images, ...]

                    gaussian_splats_vis = gaussian_predictor(input_images,
                                                        vis_data["view_to_world_transforms"][:, :cfg.data.input_images, ...],
                                                        rot_transform_quats,
                                                        focals_pixels_pred)

                    test_loop = []
                    test_loop_gt = []
                    for r_idx in range(vis_data["gt_images"].shape[1]):
                        # We don't change the input or output of the network, just the rendering cameras
                        if "focals_pixels" in vis_data.keys():
                            focals_pixels_render = vis_data["focals_pixels"][0, r_idx]
                        else:
                            focals_pixels_render = None
                        test_image = render_predicted({k: v[0].contiguous() for k, v in gaussian_splats_vis.items()}, 
                                            vis_data["world_view_transforms"][0, r_idx], 
                                            vis_data["full_proj_transforms"][0, r_idx], 
                                            vis_data["camera_centers"][0, r_idx],
                                            background,
                                            cfg,
                                            focals_pixels=focals_pixels_render)["render"]
                        test_loop_gt.append((np.clip(vis_data["gt_images"][0, r_idx].detach().cpu().numpy(), 0, 1)*255).astype(np.uint8))
                        test_loop.append((np.clip(test_image.detach().cpu().numpy(), 0, 1)*255).astype(np.uint8))
        
                    wandb.log({"rot": wandb.Video(np.asarray(test_loop), fps=20, format="mp4")},
                        step=iteration)
                    wandb.log({"rot_gt": wandb.Video(np.asarray(test_loop_gt), fps=20, format="mp4")},
                        step=iteration)

            fnames_to_save = []
            # Find out which models to save
            if (iteration + 1) % cfg.logging.ckpt_iterations == 0 and fabric.is_global_zero:
                fnames_to_save.append("model_latest.pth")
            if (iteration + 1) % cfg.logging.val_log == 0 and fabric.is_global_zero:
                torch.cuda.empty_cache()
                print("\n[ITER {}] Validating".format(iteration + 1))
                if cfg.opt.ema.use:
                    scores = evaluate_dataset(
                        ema, 
                        val_dataloader, 
                        device=device,
                        model_cfg=cfg)
                else:
                    scores = evaluate_dataset(
                        gaussian_predictor, 
                        val_dataloader, 
                        device=device,
                        model_cfg=cfg)
                wandb.log(scores, step=iteration+1)
                # save models - if the newest psnr is better than the best one,
                # overwrite best_model. Always overwrite the latest model. 
                if scores["PSNR_novel"] > best_PSNR:
                    fnames_to_save.append("model_best.pth")
                    best_PSNR = scores["PSNR_novel"]
                    print("\n[ITER {}] Saving new best checkpoint PSNR:{:.2f}".format(
                        iteration + 1, best_PSNR))
                torch.cuda.empty_cache()

            # ============ Model saving =================
            for fname_to_save in fnames_to_save:
                ckpt_save_dict = {
                                "iteration": iteration,
                                "optimizer_state_dict": optimizer.state_dict(),
                                "loss": total_loss.item(),
                                "best_PSNR": best_PSNR
                                }
                if cfg.opt.ema.use:
                    ckpt_save_dict["model_state_dict"] = ema.ema_model.state_dict()                  
                else:
                    ckpt_save_dict["model_state_dict"] = gaussian_predictor.state_dict() 
                torch.save(ckpt_save_dict, os.path.join(vis_dir, fname_to_save))

            gaussian_predictor.train()

    wandb_run.finish()

if __name__ == "__main__":
    main()
