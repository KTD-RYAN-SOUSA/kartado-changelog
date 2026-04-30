import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Semaphore, Thread
from typing import Any, Callable, List

from requests import Response, post
from rest_framework import status

from RoadLabsAPI.settings.credentials import GOTENBERG_BASE_URL

GOTENBERG_URL = f"{GOTENBERG_BASE_URL}/forms/libreoffice/convert"
TEMP_COUNTER: int = 0  # static temp name counter
TEMP_COUNTER_LOCK: Lock = Lock()  # sync counter access
FILE_LOCK: Lock = Lock()  # sync file access


def synchronized_request_pdf(
    xlsx_file: str,
    temp_name: str = None,
    callback: Callable = None,
    callback_args: tuple = (),
) -> None:
    c = 1
    data = {"merge": "true"}
    global TEMP_COUNTER

    name, _ = os.path.splitext(xlsx_file)
    pdf_name = f"{name}.pdf"
    dir_path = os.path.dirname(xlsx_file)

    if temp_name is None:
        TEMP_COUNTER_LOCK.acquire_lock()
        count = TEMP_COUNTER
        TEMP_COUNTER += 1
        temp_name = os.path.join(dir_path, f"xlsx_to_pdf_{count}.xlsx")
        TEMP_COUNTER_LOCK.release_lock()
    else:
        temp_name = os.path.join(dir_path, temp_name)

    if xlsx_file != temp_name:
        """
        temp_name and a copy of the file might be used to avoid
        modifications during the buffered read in post
        """
        FILE_LOCK.acquire_lock()
        """ This mutex might be used during the saving of the file of an
            exporting program for which the specification allows different
            files with the same name
        """
        shutil.copy(xlsx_file, temp_name)
        FILE_LOCK.release_lock()

    while True:

        try:
            files = [("files", (open(temp_name, "rb")))]
            response: Response = None
            # print(f"try {c}: {temp_name}")
            response = post(GOTENBERG_URL, data=data, files=files)
            if (
                response.status_code == status.HTTP_200_OK
                and response.headers["content-type"] == "application/pdf"
            ):
                break
        except Exception as e:
            print(e)
        time.sleep(2)
        c += 1

    FILE_LOCK.acquire_lock()
    f = open(pdf_name, "wb")
    f.write(response.content)
    f.close()
    FILE_LOCK.release_lock()
    if callback is not None:
        callback(*callback_args)

    return pdf_name


def convert_files_to_pdf(files: List[str]) -> List[str]:
    """
    Converte múltiplos arquivos Excel para PDF utilizando processamento paralelo
    com pool de 20 threads.
    """
    if not files:
        return []

    pdf_files: List[str] = []
    futures = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        # Submete todas as tarefas de conversão e armazena as futures
        for file in files:
            future = executor.submit(synchronized_request_pdf, file)
            futures.append(future)

        # Coleta os resultados das futures na ordem de submissão
        for future in futures:
            pdf_files.append(future.result())

    return pdf_files


class ThreadExecutor:
    """
    A executor service to submit
    methods execution to a thread pool.
    The return values are stored in a
    list, that can be retrieved with the
    result of all already submitted jobs.
    The thread pool uses python threads, making
    this class only suitable for IO bound
    tasks.
    Note: initially developed for pdf conversion
    """

    def __init__(self, threads: int) -> None:
        """
        Initializes the service
        param: threads: is the number of threads in
        the pool
        """
        self.__N = threads
        self.__threads: List[Thread] = []

        self.__pending: Semaphore = Semaphore(0)
        self.__pending_mtx: Lock = Lock()
        self.__pending_list: List[tuple] = []

        self.__done_list: List[Any] = []
        self.__done_mtx: Lock = Lock()

        self.__start()

    def __execute(self) -> None:
        """
        Execution method. Takes a job,
        executes and appends the return
        value to the done list.
        None is a stop command.
        """
        while True:
            self.__pending.acquire()
            self.__pending_mtx.acquire(True)
            job: tuple = self.__pending_list.pop(0)
            self.__pending_mtx.release()
            if job is None:
                break

            method = job[0]
            args = job[1:]
            print(f"__execute: {args[0]}")
            result = method(*args)

            self.__done_mtx.acquire(True)
            self.__done_list.append(result)
            self.__done_mtx.release()

    def __start(self) -> None:
        """
        Initialize and starts the execution threads
        """
        self.__threads = []
        for _ in range(self.__N):
            thread = Thread(
                target=ThreadExecutor.__execute,
                args=(self,),
            )
            self.__threads.append(thread)
            thread.start()

    def __join(self) -> None:
        """
        Submits the stop command and
        join the threads.
        It will wait for all already
        submitted jobs.
        """
        for _ in self.__threads:
            self.__submit(None)
        for thread in self.__threads:
            thread.join()

    def __del__(self) -> None:
        """
        Joins threads
        before destruction
        """
        self.__join()

    def __submit(self, value: Any) -> None:
        """
        Appends to the pending list
        """
        self.__pending_mtx.acquire(True)
        self.__pending_list.append(value)
        self.__pending_mtx.release()
        self.__pending.release()

    def submit(self, method: Callable, *args) -> None:
        """
        Submits a job. Appends to the
        pending list the tuple (method, args...).
        """
        print(f"submit: {args[0]}")
        self.__submit((method, *args))

    def get(self) -> List[Any]:
        """
        Waits all submitted jobs, joining
        the threads; gets returned values;
        restarts threads; returns all returned
        values.

        """
        self.__join()
        result = self.__done_list
        self.__start()
        self.__done_list = []
        return result
