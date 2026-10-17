This is a Qwen3.6_27B Desktop Local LLM workstation ran via PyQt5, it is using the uncencored version of the model. The workstation has the option to scrap the web using a Docker container locally-ran SearXNG search engine.
The workstation also features a vision model for image reading (no image generation).

Below are some screenshots of the final app:
![Initial load - Dark Mode](image.png)
![Initial load - Light Mode](image-1.png)
![Settings](image-2.png)
![Projects](image-3.png)
![Inside a Project](image-4.png)
![Instructions](image-5.png)

This workstation and choice of models is highly optimised for the RTX5070 (12GB) GPUs or something very similar to it (eg. RTX 4070ti, RTX5060ti-16GB variant, etc). Running this on a stronger GPU (or more VRAM) will provide better results.

To be able to run this workstation properly, follow the below steps accordingly:
1. Download the Qwen3.6-27B-UD-IQ3_XXS.gguf language model and mmproj-F16.gguf vision model from HuggingFace and place them inside a folder, name it "models".
2. Install Docker Desktop and must keep it running before turning on "Online Mode" - otherwise you won't be able to scrap the web.
