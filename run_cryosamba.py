import os
import sys
import shutil
import shutil_nfs
import json
import subprocess
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import typer
from loguru import logger
from rich import print as rprint
from rich.console import Console

app = typer.Typer()

RUNS_DIR = os.path.join(os.getcwd(), "runs")
CRYOSAMBA_DIR = os.path.dirname(__file__)


def select_gpus() -> Optional[Union[List[str], int]]:
    simple_header("GPU Selection")

    rprint(
        f"[yellow]Please note that you need a nvidia GPU to run CryoSamba. If you cannot see GPU information, your machine may not support CryoSamba.[/yellow]"
    )

    if typer.confirm("Do you want to see detailed GPU information?"):
        command1 = "nvidia-smi"
        res = subprocess.run(command1, shell=True, capture_output=True, text=True)
        print("")
        print(res.stdout)

    command2 = "nvidia-smi --query-gpu=index,utilization.gpu,memory.free,memory.total,memory.used --format=csv"
    res2 = subprocess.run(command2, shell=True, capture_output=True, text=True)

    lst_available_gpus = []
    lines = res2.stdout.split("\n")
    for i, line in enumerate(lines):
        if i == 0 or line == "":
            continue
        lst_available_gpus.append(line.split(",")[0])
    select_gpus = []
    while True:
        rprint(
            f"\n[bold]You have these GPUs left available now: [red]{lst_available_gpus}[/red] and have currently selected these GPUs: [green]{select_gpus}[/green][/bold]"
        )
        gpus = typer.prompt("Add a GPU number: (or Enter F to finish selection)")
        if gpus == "F":
            break
        if gpus in lst_available_gpus:
            select_gpus.append(gpus)
            lst_available_gpus.remove(gpus)
        else:
            rprint(f"[red]Invalid choice![/red]")

    print("")
    if len(select_gpus) == 0:
        rprint(f"[red]You didn't select any GPUs[/red]")
        return -1
    else:
        rprint(f"You have selected the following GPUs: [blue]{select_gpus}[/blue]\n")

    return select_gpus


def run_training(gpus: str, exp_name: str) -> None:
    config_path = os.path.join(RUNS_DIR, exp_name, "train_config.json")
    cmd = f"OMP_NUM_THREADS=1 CUDA_VISIBLE_DEVICES={gpus} torchrun --standalone --nproc_per_node=$(echo {gpus} | tr ',' '\\n' | wc -l) {CRYOSAMBA_DIR}/train.py --config {config_path}"
    rprint(
        f"[yellow][bold]!!! Training instructions, read before proceeding !!![/bold][/yellow]"
    )
    rprint(
        f"[bold]* You can interrupt training at any time by pressing CTRL + C, and you can resume it later by running CryoSamba again *[/bold]"
    )
    rprint(
        f"[bold]* Training will run until your specified maximum number of iterations is reached. However, you can monitor the training and validation losses and halt training when you think they have converged/stabilized * [/bold]"
    )
    rprint(
        f"[bold]* You can monitor the losses through here, through the .log file in the experiment training folder, or through TensorBoard (see README on how to run it) *[/bold] \n"
    )
    rprint(
        f"[bold]* The output of the training run will be checkpoint files containing the trained model weights. There is no denoised data output at this point yet. You can used the trained model weights to run inference on your data and then get the denoised outputs. *[/bold] \n"
    )
    if typer.confirm("Do you want to start training?"):
        rprint(f"\n[blue]***********************************************[/blue]\n")
        subprocess.run(cmd, shell=True, text=True)
    else:
        rprint(f"[red]Training aborted[/red]")


def run_inference(gpus: str, exp_name: str) -> None:
    config_path = os.path.join(RUNS_DIR, exp_name, "inference_config.json")
    cmd = f"OMP_NUM_THREADS=1 CUDA_VISIBLE_DEVICES={gpus} torchrun --standalone --nproc_per_node=$(echo {gpus} | tr ',' '\\n' | wc -l) {CRYOSAMBA_DIR}/inference.py --config {config_path}"
    rprint(
        f"[yellow][bold]!!! Inference instructions, read before proceeding !!![/bold][/yellow]"
    )
    rprint(
        f"[bold]* You can interrupt inference at any time by pressing CTRL + C, and you can resume it later by running CryoSamba again *[/bold]"
    )
    rprint(
        f"[bold]* You should have previously run a training session on this experiment in order to run inference * [/bold]"
    )
    rprint(
        f"[bold]* The denoised volume will be generated after the final iteration * [/bold] \n"
    )
    if typer.confirm("Do you want to start inference?"):
        rprint(f"\n[blue]***********************************************[/blue]\n")
        subprocess.run(cmd, shell=True, text=True)
    else:
        rprint(f"[red]Inference aborted[/red]")


def handle_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            typer.echo(f"An error occurred: {str(e)}")
            logger.exception("An exception occurred")
            raise typer.Exit(code=1)

    return wrapper


@handle_exceptions
def is_conda_installed() -> bool:
    """Run a subprocess to see if conda is installed or not"""
    try:
        subprocess.run(
            ["conda", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError:
        return False


@handle_exceptions
def is_env_active(env_name) -> bool:
    """Use conda env list to check active environments"""
    cmd = "conda env list"
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return f"{env_name}" in result.stdout


def run_command(command, shell=True):
    process = subprocess.Popen(
        command,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    output, error = process.communicate()
    if process.returncode != 0:
        typer.echo(f"Error executing command: {command}\nError: {error}", err=True)
        logger.error(f"Error executing command: {command}\nError: {error}")
    return output, error


@app.command()
@handle_exceptions
def setup_conda():
    """Setup Conda installation"""
    typer.echo("Conda Installation")
    if is_conda_installed():
        rprint(f"[green]Conda is already installed.[/green]")
    else:
        if sys.platform.startswith("linux") or sys.platform == "darwin":
            typer.echo("Conda is not installed. Installing conda ....")
            subprocess.run(
                "wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh",
                shell=True,
            )
            subprocess.run("chmod +x Miniconda3-latest-Linux-x86_64.sh", shell=True)
            subprocess.run("bash Miniconda3-latest-Linux-x86_64.sh", shell=True)
            subprocess.run("export PATH=~/miniconda3/bin:$PATH", shell=True)
            subprocess.run("source ~/.bashrc", shell=True)
        else:
            run_command(
                "powershell -Command \"(New-Object Net.WebClient).DownloadFile('https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe', 'Miniconda3-latest-Windows-x86_64.exe')\""
            )
            run_command(
                'start /wait "" Miniconda3-latest-Windows-x86_64.exe /InstallationType=JustMe /AddToPath=1 /RegisterPython=0 /S /D=%UserProfile%\\Miniconda3'
            )


@app.command()
@handle_exceptions
def setup_environment(
    env_name: str = typer.Option("cryosamba", prompt="Enter environment name")
):
    """Setup Conda environment"""
    typer.echo(f"Setting up Conda Environment: {env_name}")
    cmd = f"conda init && conda activate {env_name}"
    if is_env_active(env_name):
        typer.echo(f"Environment '{env_name}' exists.")
        subprocess.run(cmd, shell=True)
    else:
        typer.echo(f"Creating conda environment: {env_name}")
        subprocess.run(f"conda create --name {env_name} python=3.11 -y", shell=True)
        subprocess.run(cmd, shell=True)
        typer.echo("Environment has been created")
        typer.echo("**please copy the command below in the terminal.**")

        cmd = f"conda init && sleep 3 && source ~/.bashrc && conda activate {env_name} && pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 && pip install tifffile mrcfile easydict loguru tensorboard streamlit pipreqs cupy-cuda11x typer webbrowser"
        typer.echo(
            f"Say you downloaded cryosamba in your downloads folder, open a NEW terminal window and run the following commands or hit yes to run it here: \n\n{cmd} "
        )
        run_cmd = typer.prompt("Enter (y/n): ")
        while True:
            if run_cmd == "n":
                typer.echo(cmd)
                break
            elif run_cmd == "y":
                subprocess.run(cmd, shell=True, text=True)
                break


@app.command()
@handle_exceptions
def export_env():
    """Export Conda environment"""
    typer.echo("Exporting Conda Environment")
    subprocess.run("conda env export > environment.yml", shell=True)
    subprocess.run("mv environment.yml ", shell=True)
    typer.echo("Environment exported and moved to root directory.")


def ask_user(prompt: str, default: Any = None) -> Any:
    return typer.prompt(prompt, default=default)


def ask_user_int(prompt: str, min_value: int, max_value: int, default: int) -> int:
    while True:
        try:
            value = int(ask_user(prompt, default))
            if min_value <= value <= max_value:
                return value
            else:
                rprint(
                    f"[red]Please enter a value between [bold]{min_value}[/bold] and [bold]{max_value}[/bold].[/red]"
                )
        except ValueError:
            rprint(f"[red]Please enter a valid integer.[/red]")


def ask_user_int_multiple(
    prompt: str, min_value: int, max_value: int, multiple: int, default: int
) -> int:
    while True:
        try:
            value = int(ask_user(prompt, default))
            if min_value <= value <= max_value:
                if value % multiple != 0:
                    rprint(
                        f"[red]Please enter an integer value multiple of {multiple}.[/red]"
                    )
                else:
                    return value
            else:
                rprint(
                    f"[red]Please enter a value between [bold]{min_value}[/bold] and [bold]{max_value}[/bold].[/red]"
                )
        except ValueError:
            rprint(f"[red]Please enter a valid integer.[/red]")


def list_tif_files(path):
    files = []
    # List all files and directories in the specified path
    for entry in os.listdir(path):
        # Construct the full path of the entry
        full_path = os.path.join(path, entry)
        # Check if the entry is a file and ends with '.tif'
        if os.path.isfile(full_path) and entry.endswith(".tif"):
            files.append(full_path)
    return files


@app.command()
def generate_experiment(exp_name: str) -> None:

    rprint(f"[bold]Setting up new experiment [green]{exp_name}[/green][/bold]")
    rprint(
        f"[bold]Please choose experiment parameters below. Values inside brackets will be chosen by default if you press Enter without providing any input.[/bold]"
    )

    exp_path = os.path.join(RUNS_DIR, exp_name)

    # Common parameters
    train_dir = f"{exp_path}/train"
    inference_dir = f"{exp_path}/inference"

    while True:
        rprint(
            f"\n[bold]DATA PATH[/bold]: The path to a single (3D) .tif, .mrc or .rec file, or the path to a folder containing a sequence of (2D) .tif files, ordered alphanumerically matching the Z-stack order. You can use the full path or a path relative from the CryoSamba folder."
        )
        data_path = ask_user(
            "Enter your data path",
            f"data/sample_data.rec",
        )
        if not os.path.exists(data_path):
            rprint(f"[red]Data path is invalid. Try again.[/red]")
        else:
            if os.path.isfile(data_path):
                extension = os.path.splitext(data_path)[1]
                if extension not in [".mrc", ".rec", ".tif"]:
                    rprint(
                        f"[red]Extension [bold]{extension}[/bold] is not supported. Try another path.[/red]"
                    )
                else:
                    break
            elif os.path.isdir(data_path):
                files = list_tif_files(data_path)
                if len(files) == 0:
                    rprint(
                        f"[red]Your folder does not contain any tif files. Only sequences of tif files are currently supported. Try another path.[/red]"
                    )
                else:
                    break

    # Training specific parameters
    rprint(
        f"\n[bold]MAXIMUM FRAME GAP FOR TRAINING[/bold]: explained in the manuscript. We empirically set values of 3, 6 and 10 for data at resolutions of 15.72, 7.86 and 2.62 Angstroms/voxel, respectively. For different resolutions, try a reasonable value interpolated from the reference ones."
    )
    train_max_frame_gap = ask_user_int("Enter Maximum Frame Gap for Training", 1, 40, 3)
    rprint(
        f"\n[bold]NUMBER OF ITERATIONS[/bold]: for how many iterations the training session will run. This is an upper limit, and you can halt training before that."
    )
    num_iters = ask_user_int(
        "Enter the number of iterations you want to run", 1000, 200000, 50000
    )
    rprint(
        f"\n[bold]BATCH SIZE[/bold]: number of data points passed at once to the GPUs. A higher number leads to faster training, but the whole batch might not fit into your GPU's memory, leading to out-of-memory errors or severe slowdowns. If you're getting these, try to decrease the batch size until they disappear. This number should be an even integer."
    )
    batch_size = ask_user_int_multiple("Enter the batch size", 2, 256, 2, 8)
    # Inference specific parameters
    rprint(
        f"\n[bold]MAXIMUM FRAME GAP FOR INFERENCE[/bold]: explained in the manuscript. We recommend using twice the value used for training."
    )
    inference_max_frame_gap = ask_user_int(
        "Enter Maximum Frame Gap for Inference", 1, 80, train_max_frame_gap * 2
    )
    rprint(
        f"\n[bold]TEST-TIME AUGMENTATION[/bold]: explained in the manuscript. Enabling it leads to slightly better denoising quality at the cost of much longer inference times."
    )
    tta = typer.confirm(
        "Enable Test Time Augmentation (TTA) for inference (disabled by default)?",
        default=False,
    )
    rprint(
        f"\n[bold]TRAINING EARLY STOPPING[/bold]: If activated, training will be halted if, starting after 20 epochs, the validation loss doesn't decrease for at least 3 consecutive epochs."
    )
    early_stopping = typer.confirm(
        "Enable Early Stopping (disabled by default)?", default=False
    )
    rprint(
        f"\n[yellow][bold]ADVANCED PARAMETERS[/bold]: only recommended for experienced users.[/yellow]"
    )
    advanced = typer.confirm(
        "Do you want to set up advanced parameters (No by default)?", default=False
    )

    train_data_patch_shape_y = 256
    train_data_patch_shape_x = 256
    train_data_patch_overlap_y = 16
    train_data_patch_overlap_x = 16
    train_data_split_ratio = 0.95
    train_data_num_workers = 4

    train_load_ckpt_path = None
    train_print_freq = 100
    train_save_freq = 1000
    train_val_freq = 500
    train_warmup_iters = 300
    train_mixed_precision = True
    train_compile = False

    optimizer_lr = 2e-4
    optimizer_lr_decay = 0.99995
    optimizer_weight_decay = 0.0001
    optimizer_epsilon = 1e-08
    optimizer_betas_0 = 0.9
    optimizer_betas_1 = 0.999

    biflownet_pyr_dim = 24
    biflownet_pyr_level = 3
    biflownet_corr_radius = 4
    biflownet_kernel_size = 3
    biflownet_warp_type = "soft_splat"
    biflownet_padding_mode = "reflect"
    biflownet_fix_params = False

    fusionnet_num_channels = 16
    fusionnet_padding_mode = "reflect"
    fusionnet_fix_params = False

    inference_data_patch_shape_y = 256
    inference_data_patch_shape_x = 256
    inference_data_patch_overlap_y = 16
    inference_data_patch_overlap_x = 16
    inference_data_num_workers = 4

    inference_output_format = "same"
    inference_load_ckpt_name = None
    inference_pyr_level = 3
    inference_mixed_precision = True
    inference_compile = False

    if advanced:
        simple_header(f"[yellow] Advanced Parameters [/yellow]")
        rprint(
            f"For explanations, refer to the [bold]advanced instructions[/bold] or the [bold]manuscript[/bold]."
        )
        train_data_patch_shape_y = ask_user_int_multiple(
            "Enter train_data.patch_shape on Y", 32, 1024, 32, 256
        )
        train_data_patch_shape_x = ask_user_int_multiple(
            "Enter train_data.patch_shape on X", 32, 1024, 32, 256
        )
        train_data_patch_overlap_y = ask_user_int_multiple(
            "Enter train_data.patch_overlap on Y", 0, 512, 4, 16
        )
        train_data_patch_overlap_x = ask_user_int_multiple(
            "Enter train_data.patch_overlap on X", 0, 512, 4, 16
        )
        train_data_split_ratio = 0.95
        train_data_num_workers = ask_user_int("Enter train_data.num_workers", 0, 512, 4)

        train_print_freq = ask_user_int("Enter train.print_freq", 1, 10000, 100)
        train_save_freq = ask_user_int("Enter train.save_freq", 1, 10000, 1000)
        train_val_freq = ask_user_int("Enter train.val_freq", 1, 10000, 500)
        train_warmup_iters = ask_user_int("Enter train.warmup_iters", 1, 10000, 300)
        train_mixed_precision = ask_user("Enter train.mixed_precision", True)
        train_compile = ask_user("Enter train.compile", False)

        optimizer_lr = ask_user("Enter optimizer.lr", 2e-4)
        optimizer_lr_decay = ask_user("Enter optimizer.lr_decay", 0.99995)
        optimizer_weight_decay = ask_user("Enter optimizer.weight_decay", 0.0001)
        optimizer_epsilon = ask_user("Enter optimizer.epsilon", 1e-08)
        optimizer_betas_0 = ask_user("Enter optimizer.betas_0", 0.9)
        optimizer_betas_1 = ask_user("Enter optimizer.betas_1", 0.999)

        biflownet_pyr_dim = ask_user_int_multiple(
            "Enter biflownet.pyr_dim", 4, 128, 4, 24
        )
        biflownet_pyr_level = ask_user_int("Enter biflownet.pyr_level", 1, 20, 3)
        biflownet_corr_radius = ask_user_int("Enter biflownet.corr_radius", 1, 20, 4)
        biflownet_kernel_size = ask_user_int("Enter biflownet.kernel_size", 1, 20, 3)
        biflownet_warp_type = ask_user("Enter biflownet.warp_type", "soft_splat")
        biflownet_padding_mode = ask_user("Enter biflownet.padding_mode", "reflect")
        biflownet_fix_params = ask_user("Enter biflownet.fix_params", False)

        fusionnet_num_channels = ask_user_int_multiple(
            "Enter fusionnet.num_channels", 4, 128, 4, 16
        )
        fusionnet_padding_mode = ask_user("Enter fusionnet.padding_mode", "reflect")
        fusionnet_fix_params = ask_user("Enter fusionnet.fix_params", False)

        inference_data_patch_shape_y = ask_user_int_multiple(
            "Enter inference_data.patch_shape on Y", 32, 1024, 32, 256
        )
        inference_data_patch_shape_x = ask_user_int_multiple(
            "Enter inference_data.patch_shape on Y", 32, 1024, 32, 256
        )
        inference_data_patch_overlap_y = ask_user_int_multiple(
            "Enter inference_data.patch_overlap on Y", 0, 512, 4, 16
        )
        inference_data_patch_overlap_x = ask_user_int_multiple(
            "Enter inference_data.patch_overlap on Y", 0, 512, 4, 16
        )
        inference_data_num_workers = ask_user_int(
            "Enter inference_data.num_workers", 0, 512, 4
        )

        inference_output_format = ask_user("Enter inference.output_format", "same")
        inference_pyr_level = ask_user_int("Enter inference.pyr_level", 1, 20, 3)
        inference_mixed_precision = ask_user("Enter inference.mixed_precision", True)
        inference_compile = ask_user("Enter inference.compile", False)

    # Generate training config
    train_config = {
        "train_dir": train_dir,
        "data_path": data_path,
        "train_data": {
            "max_frame_gap": train_max_frame_gap,
            "patch_shape": [train_data_patch_shape_y, train_data_patch_shape_x],
            "patch_overlap": [train_data_patch_overlap_y, train_data_patch_overlap_x],
            "split_ratio": train_data_split_ratio,
            "batch_size": batch_size,
            "num_workers": train_data_num_workers,
        },
        "train": {
            "num_iters": num_iters,
            "load_ckpt_path": train_load_ckpt_path,
            "print_freq": train_print_freq,
            "save_freq": train_save_freq,
            "val_freq": train_val_freq,
            "warmup_iters": train_warmup_iters,
            "mixed_precision": train_mixed_precision,
            "compile": train_compile,
            "do_early_stopping": early_stopping,
        },
        "optimizer": {
            "lr": optimizer_lr,
            "lr_decay": optimizer_lr_decay,
            "weight_decay": optimizer_weight_decay,
            "epsilon": optimizer_epsilon,
            "betas": [optimizer_betas_0, optimizer_betas_1],
        },
        "biflownet": {
            "pyr_dim": biflownet_pyr_dim,
            "pyr_level": biflownet_pyr_level,
            "corr_radius": biflownet_corr_radius,
            "kernel_size": biflownet_kernel_size,
            "warp_type": biflownet_warp_type,
            "padding_mode": biflownet_padding_mode,
            "fix_params": biflownet_fix_params,
        },
        "fusionnet": {
            "num_channels": fusionnet_num_channels,
            "padding_mode": fusionnet_padding_mode,
            "fix_params": fusionnet_fix_params,
        },
    }

    # Generate inference config
    inference_config = {
        "train_dir": train_dir,
        "data_path": data_path,
        "inference_dir": inference_dir,
        "inference_data": {
            "max_frame_gap": inference_max_frame_gap,
            "patch_shape": [inference_data_patch_shape_y, inference_data_patch_shape_x],
            "patch_overlap": [
                inference_data_patch_overlap_y,
                inference_data_patch_overlap_x,
            ],
            "batch_size": batch_size,
            "num_workers": inference_data_num_workers,
        },
        "inference": {
            "output_format": inference_output_format,
            "load_ckpt_name": inference_load_ckpt_name,
            "pyr_level": inference_pyr_level,
            "mixed_precision": inference_mixed_precision,
            "TTA": tta,
            "compile": inference_compile,
        },
    }

    os.makedirs(f"runs/{exp_name}", exist_ok=True)

    # Save configs to files
    with open(f"{exp_path}/train_config.json", "w") as f:
        json.dump(train_config, f, indent=4)

    with open(f"{exp_path}/inference_config.json", "w") as f:
        json.dump(inference_config, f, indent=4)

    simple_header(f"Experiment [green]{exp_name}[/green] created")


def return_screen() -> None:
    if typer.confirm("Return to main menu?", default=True):
        clear_screen()
        main_menu()
    else:
        exit_screen()


def return_screen_exp_manager() -> None:
    if typer.confirm("Return to experiment manager?", default=True):
        clear_screen()
        experiment_menu()
    else:
        return_screen()


def exit_screen() -> None:
    rprint("[bold]Thank you for using CryoSamba. Goodbye![/bold]")
    quit()


def title_screen() -> None:
    rprint("")
    rprint(
        "[green] ██████╗██████╗ ██╗   ██╗ ██████╗[/green] [yellow]███████╗ █████╗ ███╗   ███╗██████╗  █████╗[/yellow]"
    )
    rprint(
        "[green]██╔════╝██╔══██╗╚██╗ ██╔╝██╔═══██╗[/green][yellow]██╔════╝██╔══██╗████╗ ████║██╔══██╗██╔══██╗[/yellow]"
    )
    rprint(
        "[green]██║     ██████╔╝ ╚████╔╝ ██║   ██║[/green][yellow]███████╗███████║██╔████╔██║██████╔╝███████║[/yellow]"
    )
    rprint(
        "[green]██║     ██╔══██╗  ╚██╔╝  ██║   ██║[/green][yellow]╚════██║██╔══██║██║╚██╔╝██║██╔══██╗██╔══██║[/yellow]"
    )
    rprint(
        "[green]╚██████╗██║  ██║   ██║   ╚██████╔╝[/green][yellow]███████║██║  ██║██║ ╚═╝ ██║██████╔╝██║  ██║[/yellow]"
    )
    rprint(
        "[green] ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ [/green][yellow]╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═════╝ ╚═╝  ╚═╝[/yellow]"
    )
    rprint("")
    rprint("[bold]Welcome to CryoSamba [white]v1.0[/white] [/bold]")
    rprint(
        "[bold]by Kirchhausen Lab [blue](https://kirchhausen.hms.harvard.edu/)[/blue][/bold]"
    )
    print("")
    rprint(
        "Please read the instructions carefully. If you experience any issues reach out to "
    )
    rprint("[bold]Jose Costa-Filho[/bold] @ joseinacio@tklab.hms.harvard.edu")
    rprint("[bold]Arkash Jain[/bold] @ arkash@tklab.hms.harvard.edu")
    rprint("We appreciate all feedback!")


def clear_screen() -> None:
    os.system("clear")


@app.command()
def main():

    clear_screen()

    main_menu()


def main_menu() -> None:

    title_screen()

    rprint(f"\n[bold]*** MAIN MENU ***[/bold]\n")

    steps = [
        f"[bold]|1| Manage experiments[/bold]",
        f"[bold]|2| Run training[/bold]",
        f"[bold]|3| Run inference[/bold]",
        f"[bold]|4| Exit[/bold]",
    ]

    if not os.path.exists(RUNS_DIR):
        os.makedirs(RUNS_DIR)
    exp_list = list_non_hidden_files(RUNS_DIR)
    if len(exp_list) == 0:
        steps[0] = f"[bold]|1| Manage experiments [red](start here!)[/red][/bold]"

    for step in steps:
        rprint(step)

    print("")
    while True:
        input_cmd = typer.prompt("Choose an option [1/2/3/4]")
        if input_cmd == "1":
            clear_screen()
            experiment_menu()
            break
        elif input_cmd == "2":
            clear_screen()
            run_cryosamba("Training")
            break
        elif input_cmd == "3":
            clear_screen()
            run_cryosamba("Inference")
            break
        elif input_cmd == "4":
            exit_screen()
            break
        else:
            rprint("[red]Invalid option. Please choose either 1, 2, 3 or 4.[/red]")


def simple_header(message) -> None:
    rprint(f"\n[bold]*** {message} ***[/bold]\n")


def setup_cryosamba() -> None:
    simple_header("CryoSamba Setup")

    if typer.confirm("Do you want to setup Conda?"):
        setup_conda()

    if typer.confirm("Do you want to setup the environment?"):
        env_name = typer.prompt("Enter environment name", default="cryosamba")
        setup_environment(env_name)

    if typer.confirm("Do you want to export the environment? (Optional)"):
        export_env()

    rprint("[green]CryoSamba setup finished[/green]")
    return_screen()


def show_exp_list() -> None:
    rprint(f"Your experiments are stored at [bold]{RUNS_DIR}[/bold]")
    exp_list = list_non_hidden_files(RUNS_DIR)
    if len(exp_list) == 0:
        rprint(f"You have no existing experiments.")
    else:
        rprint(f"You have the following experiments: [bold]{sorted(exp_list)}[/bold]")


def experiment_menu() -> None:
    simple_header("Experiment Manager")

    show_exp_list()

    steps = [
        f"[bold]|1| Create a new experiment[/bold]",
        f"[bold]|2| Delete an experiment[/bold]",
        f"[bold]|3| Return to Main Menu[/bold]",
    ]

    print("")
    for step in steps:
        rprint(step)

    print("")
    while True:
        input_cmd = typer.prompt("Choose an option [1/2/3]")
        if input_cmd == "1":
            clear_screen()
            setup_experiment()
            break
        elif input_cmd == "2":
            exp_list = list_non_hidden_files(RUNS_DIR)
            if len(exp_list) == 0:
                rprint(f"You have no existing experiments to delete.")
            else:
                clear_screen()
                delete_experiment()
                break
        elif input_cmd == "3":
            clear_screen()
            main_menu()
            break
        else:
            rprint("[red]Invalid option. Please choose either 1, 2 or 3.[/red]")


def setup_experiment() -> None:
    simple_header("New Experiment Setup")

    while True:
        exp_name = typer.prompt(
            "Please enter the new experiment name (or enter E to Exit)"
        )
        if exp_name == "E":
            break
        exp_path = os.path.join(RUNS_DIR, exp_name)
        if os.path.exists(exp_path):
            rprint(
                f"[red]Experiment [bold]{exp_name}[/bold] already exists. Please choose a new name.[/red]"
            )
        else:
            generate_experiment(exp_name)
            break
    return_screen_exp_manager()


def delete_experiment() -> None:
    simple_header("Experiment Deletion (be careful!)")

    while True:
        show_exp_list()
        exp_name = typer.prompt(
            "Please enter the name of the experiment you want to delete (or enter E to Exit)"
        )
        if exp_name == "E":
            break
        exp_path = os.path.join(RUNS_DIR, exp_name)
        if not os.path.exists(exp_path):
            rprint(
                f"[red]Experiment [bold]{exp_name}[/bold] not found. Please check the experiment name and try again.[/red]"
            )
        else:
            rprint(f"Experiment [bold]{exp_name}[/bold] found.")
            if typer.confirm(
                f"Do you really want to delete experiment {exp_name} and all its contents (config files, trained models, denoised results)?"
            ):
                shutil.rmtree(exp_path)
                rprint(f"Experiment [bold]{exp_name}[/bold] successfully deleted.")
    return_screen_exp_manager()


def list_non_hidden_files(path):
    non_hidden_files = [file for file in os.listdir(path) if not file.startswith(".")]
    return non_hidden_files


def run_cryosamba(mode) -> None:
    simple_header(f"CryoSamba {mode}")

    if not os.path.exists(RUNS_DIR):
        os.makedirs(RUNS_DIR)

    rprint(f"Your experiments are stored at [bold]{RUNS_DIR}[/bold]")
    exp_list = list_non_hidden_files(RUNS_DIR)
    if len(exp_list) == 0:
        rprint(
            f"[red]You have no existing experiments. Set up a new experiment via the main menu.[/red]"
        )
        return_screen()
    else:
        rprint(f"You have the following experiments: [bold]{sorted(exp_list)}[/bold]")

    while True:
        exp_name = typer.prompt("Please enter the experiment name (or enter E to Exit)")
        if exp_name == "E":
            break
        exp_path = os.path.join(RUNS_DIR, exp_name)
        if not os.path.exists(exp_path):
            rprint(
                f"[red]Experiment [bold]{exp_name}[/bold] not found. Please check the experiment name and try again.[/red]"
            )
        else:
            rprint(f"* Experiment [green]{exp_name}[/green] selected *")
            selected_gpus = select_gpus()
            if selected_gpus != -1:
                if mode == "Training":
                    run_training(",".join(selected_gpus), exp_name)
                elif mode == "Inference":
                    run_inference(",".join(selected_gpus), exp_name)
            break

    return_screen()


if __name__ == "__main__":
    typer.run(main)
