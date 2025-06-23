
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import requests
from cachetools import TTLCache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
import json
import base64
import subprocess
import tempfile
import shutil
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuração de cache (mantém por 1 hora)
cache = TTLCache(maxsize=1000, ttl=3600)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day"]
)

ANGOLA_API_BASE_URL = os.environ.get('ANGOLA_API_BASE_URL', 'https://angolaapi.onrender.com')

def parse_malformed_response(response_text):
    """Tenta extrair informações de uma resposta JSON malformada"""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning(f"Resposta JSON malformada recebida: {response_text}")
        if 'sucesstruemessage' in response_text.lower():
            if 'valid identity card' in response_text.lower():
                return {
                    'success': True,
                    'message': 'This is an Angola valid identity card'
                }
            elif 'invalid' in response_text.lower():
                return {
                    'success': False,
                    'message': 'Invalid identity card'
                }
        return {
            'success': False,
            'message': 'Resposta da API externa inválida'
        }

@app.route('/validate-bi/<bi_number>')
@limiter.limit("10 per minute")
def validate_bi(bi_number):
    logger.info(f"Validando BI: {bi_number}")
    if bi_number in cache:
        logger.info(f"BI {bi_number} encontrado no cache")
        return jsonify(cache[bi_number])
    
    try:
        api_url = f'{ANGOLA_API_BASE_URL}/api/v1/validate/bi/{bi_number}'
        logger.info(f"Fazendo requisição para: {api_url}")
        response = requests.get(api_url, timeout=30)
        logger.info(f"Status da resposta: {response.status_code}")
        logger.info(f"Resposta bruta: {response.text}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"Resposta parsed com sucesso: {result}")
            except json.JSONDecodeError:
                logger.warning("Falhou ao fazer parse JSON, usando parser customizado")
                result = parse_malformed_response(response.text)
            
            normalized_result = {
                'success': result.get('sucess', result.get('success', False)),
                'message': result.get('message', 'BI processado')
            }
            
            logger.info(f"Resultado normalizado: {normalized_result}")
            cache[bi_number] = normalized_result
            return jsonify(normalized_result), 200
            
        elif response.status_code == 503:
            logger.error(f"API externa indisponível (503) para BI: {bi_number}")
            return jsonify({
                'success': False,
                'error-message': 'Serviço de validação indisponível. Tente novamente em alguns minutos.'
            }), 503
            
        else:
            logger.error(f"Erro na API externa: Status {response.status_code}, Resposta: {response.text}")
            try:
                error_data = response.json()
                message = error_data.get('message', f'Erro na API externa (Status: {response.status_code})')
            except json.JSONDecodeError:
                message = f'Erro na API externa (Status: {response.status_code})'
            return jsonify({
                'success': False,
                'error-message': message
            }), response.status_code
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout na validação do BI: {bi_number}")
        return jsonify({
            'success': False,
            'error-message': 'Timeout na validação. Tente novamente.'
        }), 504
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Erro de conexão na validação do BI: {bi_number}")
        return jsonify({
            'success': False,
            'error-message': 'Erro de conexão com o serviço de validação.'
        }), 503

    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de requisição na validação do BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'error-message': f'Erro na requisição: {str(e)}'
        }), 500

    except Exception as e:
        logger.error(f"Erro interno na validação do BI {bi_number}: {str(e)}")
        return jsonify({
            'success': False,
            'error-message': f'Erro interno do servidor: {str(e)}'
        }), 500

@app.route('/generate-pdf', methods=['POST'])
@limiter.limit("5 per minute")
def generate_pdf():
    logger.info("Recebendo solicitação para gerar PDF")
    try:
        report_data = request.json.get('reportData')
        if not report_data:
            raise ValueError("Dados do relatório não fornecidos")

        # Criar diretório temporário
        temp_dir = tempfile.mkdtemp()
        images_dir = os.path.join(temp_dir, 'images')
        os.makedirs(images_dir)

        # Salvar imagens dos gráficos
        charts = report_data.get('charts', {})
        for chart_id, data_url in charts.items():
            base64_data = data_url.replace('data:image/png;base64,', '')
            with open(os.path.join(images_dir, f'{chart_id}.png'), 'wb') as f:
                f.write(base64.decode(base64_data))

        # Carregar template LaTeX
        latex_template = r"""
        \documentclass[a4paper,10pt]{article}
        \usepackage[margin=1in]{geometry}
        \usepackage{graphicx}
        \usepackage{xcolor}
        \usepackage{booktabs}
        \usepackage{tabularx}
        \usepackage{titling}
        \usepackage{parskip}
        \usepackage{amsmath}
        \usepackage{hyperref}
        \definecolor{PrimaryColor}{RGB}{34,197,94}
        \definecolor{LightText}{RGB}{243,244,246}
        \definecolor{DarkBackground}{RGB}{31,41,55}
        \definecolor{DarkCard}{RGB}{45,55,72}
        \usepackage{noto}
        \renewcommand{\familydefault}{\sfdefault}
        \hypersetup{
            colorlinks=true,
            linkcolor=PrimaryColor,
            urlcolor=PrimaryColor,
            citecolor=PrimaryColor
        }
        \title{\textbf{Relatório de Dashboard FixABairro}}
        \author{FixABairro Team}
        \date{\reportDate}
        \begin{document}
        \begin{titlepage}
            \centering
            \vspace*{2cm}
            \includegraphics[width=0.3\textwidth]{logo.png}
            \vspace{1cm}
            \Huge \textbf{Relatório de Dashboard FixABairro} \\
            \vspace{0.5cm}
            \Large \textit{Análise de Problemas Reportados}
            \vspace{1cm}
            \large \textbf{Data:} \reportDate
            \vspace{2cm}
            \normalsize
            Preparado por: FixABairro Team\\
            \url{https://fixabairro.netlify.app}
            \vfill
        \end{titlepage}
        \section*{Resumo Executivo}
        \addcontentsline{toc}{section}{Resumo Executivo}
        Este relatório apresenta uma visão geral dos problemas reportados na plataforma FixABairro até \reportDate. Inclui métricas-chave, análise por categoria, urgência, tendência temporal, uma lista de problemas recentes e validação de identidade.
        \section{Métricas Gerais}
        \begin{tabularx}{\textwidth}{l|X}
            \toprule
            \textbf{Métrica} & \textbf{Valor} \\
            \midrule
            Total de Problemas & \totalProblems \\
            Problemas Abertos & \openProblems \\
            Em Andamento & \inProgressProblems \\
            Problemas Resolvidos & \resolvedProblems \\
            \bottomrule
        \end{tabularx}
        \section{Validação de Identidade}
        \begin{tabularx}{\textwidth}{l|X}
            \toprule
            \textbf{Campo} & \textbf{Valor} \\
            \midrule
            Número do BI & \biNumber \\
            Status & \biStatus \\
            Mensagem & \biMessage \\
            \bottomrule
        \end{tabularx}
        \section{Análise Gráfica}
        \subsection{Problemas por Categoria}
        \begin{figure}[h]
            \centering
            \includegraphics[width=0.8\textwidth]{images/categoryChart.png}
            \caption{Distribuição de problemas por categoria.}
        \end{figure}
        \subsection{Distribuição de Urgência}
        \begin{figure}[h]
            \centering
            \includegraphics[width=0.8\textwidth]{images/urgencyChart.png}
            \caption{Distribuição de problemas por nível de urgência.}
        \end{figure}
        \subsection{Problemas ao Longo do Tempo}
        \begin{figure}[h]
            \centering
            \includegraphics[width=0.8\textwidth]{images/timeChart.png}
            \caption{Tendência de problemas reportados ao longo do tempo.}
        \end{figure}
        \section{Problemas Recentes}
        \begin{tabularx}{\textwidth}{X|X|X|X|X|X}
            \toprule
            \textbf{Título} & \textbf{Categoria} & \textbf{Urgência} & \textbf{Status} & \textbf{Data} & \textbf{Bairro} \\
            \midrule
            \tableRows
            \bottomrule
        \end{tabularx}
        \section*{Conclusão}
        \addcontentsline{toc}{section}{Conclusão}
        Este relatório consolida as informações do dashboard FixABairro, fornecendo insights valiosos para a gestão de problemas e validação de identidade. Para mais detalhes, acesse a plataforma em \url{https://fixabairro.netlify.app}.
        \end{document}
        """

        # Substituir placeholders
        metrics = report_data.get('metrics', {})
        bi_validation = report_data.get('biValidation', {})
        table_rows = report_data.get('table', [])
        latex_content = (
            latex_template
            .replace(r'\reportDate', report_data.get('date', datetime.now().strftime('%d de %B de %Y')))
            .replace(r'\totalProblems', metrics.get('totalProblems', '0'))
            .replace(r'\openProblems', metrics.get('openProblems', '0'))
            .replace(r'\inProgressProblems', metrics.get('inProgressProblems', '0'))
            .replace(r'\resolvedProblems', metrics.get('resolvedProblems', '0'))
            .replace(r'\biNumber', bi_validation.get('biNumber', 'N/A'))
            .replace(r'\biStatus', 'Válido' if bi_validation.get('success', False) else 'Inválido')
            .replace(r'\biMessage', bi_validation.get('message', 'Nenhuma validação realizada'))
            .replace(r'\tableRows', '\n'.join([' & '.join(row) + r' \\ \hline' for row in table_rows]))
        )

        # Salvar template LaTeX
        latex_file = os.path.join(temp_dir, 'output.tex')
        with open(latex_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        # Copiar logo (substitua 'logo.png' pelo caminho real)
        shutil.copy('logo.png', os.path.join(temp_dir, 'logo.png'))

        # Compilar LaTeX
        subprocess.run(['latexmk', '-pdf', 'output.tex'], cwd=temp_dir, check=True)

        # Enviar PDF
        pdf_file = os.path.join(temp_dir, 'output.pdf')
        response = send_file(pdf_file, as_attachment=True, download_name='relatorio_fixabairro.pdf')

        # Limpar diretório temporário
        shutil.rmtree(temp_dir, ignore_errors=True)
        return response

    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {str(e)}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({
            'success': False,
            'error-message': f'Erro ao gerar PDF: {str(e)}'
        }), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/cache-stats')
def cache_stats():
    return jsonify({
        'cache_size': len(cache),
        'max_size': cache.maxsize,
        'ttl': cache.ttl
    }), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
