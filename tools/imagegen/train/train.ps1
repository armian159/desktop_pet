# Trains the phoebechobi character LoRA. Unload Ollama models and ComfyUI first (8 GB VRAM).
#   powershell -ExecutionPolicy Bypass -File D:\study\ComfyUI\train\train.ps1
$env:PYTHONIOENCODING = 'utf-8'
Set-Location D:\study\ComfyUI\sd-scripts
$comfy = 'D:\study\ComfyUI\ComfyUI_windows_portable\ComfyUI\models'
& .\.venv\Scripts\python.exe sdxl_train_network.py `
  --pretrained_model_name_or_path "$comfy\checkpoints\Illustrious-XL-v1.0.safetensors" `
  --dataset_config 'D:\study\ComfyUI\train\dataset.toml' `
  --output_dir "$comfy\loras" `
  --output_name phoebechobi `
  --save_model_as safetensors `
  --network_module networks.lora --network_dim 8 --network_alpha 4 `
  --network_train_unet_only `
  --learning_rate 1e-4 --optimizer_type AdamW8bit `
  --lr_scheduler cosine --lr_warmup_steps 50 `
  --max_train_epochs 10 --save_every_n_epochs 2 `
  --mixed_precision fp16 --save_precision fp16 --no_half_vae `
  --cache_latents --cache_latents_to_disk --cache_text_encoder_outputs `
  --gradient_checkpointing --sdpa `
  --min_snr_gamma 5 --seed 42 `
  --max_data_loader_n_workers 0 2>&1
"train exit $LASTEXITCODE"
