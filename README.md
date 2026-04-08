# CamIA - VibeCoding

> Em construção

Detector de movimento por câmera com análise de IA via [Groq](https://groq.com).

## Stack

- **Python 3.10+**
- **Flask** — servidor web e streaming de vídeo
- **OpenCV** — captura da webcam e detecção de movimento (MOG2)
- **NumPy** — manipulação de arrays de imagem
- **Groq API** — inferência de IA (modelo `meta-llama/llama-4-scout-17b-16e-instruct`) - use outro modelo/llm melhor, se preferir
- **python-dotenv** — gerenciamento de variáveis de ambiente

## Como funciona

1. Captura a webcam em tempo real com OpenCV
2. Detecta movimento usando subtração de fundo (MOG2)
3. Envia o frame capturado para a Groq API (Llama 4 com visão)
4. Exibe a análise da IA no site ao lado do vídeo

## Pré-requisitos

- Python 3.10+
- API key da Groq (grátis em [console.groq.com](https://console.groq.com))

## Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/zGabriel-Passos/CamIA.git
cd CamIA

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Configure a API key
cp .env.example .env
# Edite o .env e coloque sua chave da Groq
```

> **Importante:** Renomeie `.env.example` para `.env` — o código lê o arquivo `.env`, não o `.env.example`.

## Uso

```bash
python app.py
```

Acesse `http://localhost:5000` no navegador.

## Licença

MIT
