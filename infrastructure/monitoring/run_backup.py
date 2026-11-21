import subprocess
import sys
from pathlib import Path


CONTAINERS = [
    "mlops-prometheus",
    "mlops-grafana",
]

SCRIPT = Path(__file__).with_name("backup_to_s3.py")


def docker(*args):
    subprocess.run(
        ["sudo", "docker", *args],
        check=True,
    )


def main():
    stopped = []
    backup_error = None
    restart_errors = []

    try:
        for container in CONTAINERS:
            print(f"Останавливаем {container}", flush=True)
            docker("stop", container)
            stopped.append(container)

        print("Создаём резервные копии и загружаем в S3", flush=True)
        subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=True,
        )

        print("Резервное копирование завершено", flush=True)

    except Exception as exc:
        backup_error = exc
        print(f"Ошибка резервного копирования: {exc}", flush=True)

    finally:
        # Пытаемся запустить каждый контейнер независимо от ошибок.
        for container in reversed(CONTAINERS):
            try:
                print(f"Проверяем запуск {container}", flush=True)
                docker("start", container)
            except Exception as exc:
                restart_errors.append(f"{container}: {exc}")
                print(f"Ошибка запуска {container}: {exc}", flush=True)

    if backup_error or restart_errors:
        if restart_errors:
            print("Не удалось запустить: " + "; ".join(restart_errors))
        sys.exit(1)

    print("Все сервисы мониторинга запущены", flush=True)


if __name__ == "__main__":
    main()
