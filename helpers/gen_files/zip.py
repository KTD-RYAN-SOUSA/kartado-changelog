import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Dict
from zipfile import ZipFile

import requests
from django.conf import settings

from helpers.aws import upload_to_s3


def request_and_zip(
    file_data: str,
    zip_file,
    type_files: str = None,
    source: str = "links",
):
    try:
        # Faz a solicitação GET para cada URL
        if source == "links":
            response = requests.get(file_data["url"])

            # Verifica se a solicitação foi bem-sucedida (código de status 200)
            if response.status_code == 200:
                zip_file.writestr(file_data["file_name"], response.content)
                return True
        elif source == "views":
            if file_data.status_code == 200:
                file_name = (
                    file_data.headers.get("Content-Disposition", "")
                    .replace('"', "")
                    .replace("filename=", "")
                )
                zip_file.writestr(file_name, file_data.content)
                return True

        print(file_data, "\n")

    except requests.RequestException as e:
        # Retorna mensagens de erro, se houver algum problema com a solicitação
        print(f"Error making request to {file_data}: {e}")

    return False


def download_file_and_zip(
    files_data: Dict,
    zip_filename: str = "tmp.zip",
    type_files: str = None,
) -> str:
    url_s3 = None
    have_pdf = False
    # Obtenha o caminho absoluto do diretório atual
    directory_path = "/tmp/temp_zip_files/"
    os.makedirs(directory_path, exist_ok=True)
    current_directory = directory_path
    # Construa o caminho completo do arquivo
    zip_file_path = os.path.join(current_directory, zip_filename)
    # Número máximo de threads que serão usadas simultaneamente
    max_threads = 1
    if files_data:
        with BytesIO() as zip_buffer:  # Cria um buffer de bytes em memória
            with ZipFile(zip_buffer, "w") as zip_file:
                try:
                    with ThreadPoolExecutor(max_threads) as executor:
                        # O método map espera uma função e uma lista de argumentos, então usamos uma função lambda
                        results = []
                        for file_source in files_data:
                            results += list(
                                executor.map(
                                    lambda file_data: request_and_zip(
                                        file_data, zip_file, type_files, file_source
                                    ),
                                    files_data[file_source],
                                )
                            )

                        have_pdf = any(results)

                except Exception as e:
                    print(e)
                    pass

            if have_pdf:
                with open(zip_file_path, "wb") as f:
                    f.write(zip_buffer.getvalue())

                    data = dict(
                        file_path=zip_file_path,
                        bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                        custom_filename=zip_filename,
                    )

                    url_s3 = upload_to_s3(**data)
        for file_name in os.listdir(current_directory):
            os.remove(current_directory + file_name)
    return url_s3
