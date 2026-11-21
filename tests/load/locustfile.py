from locust import HttpUser, constant, task


class EcommercePredictionUser(HttpUser):
    # Пауза между запросами одного виртуального пользователя.
    wait_time = constant(1)

    @task
    def predict_purchase(self):
        payload = {
            "views": 10,
            "purchases": 2,
            "ctr": 0.2,
            "hour": 14,
            "weekday": 3,
            "categoryid": 100,
            "available": 1,
        }

        with self.client.post(
            "/predict_purchase",
            json=payload,
            name="/predict_purchase",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                return

            try:
                data = response.json()
                probability = data["purchase_probability"]
                model_version = data["model_version"]

                if not 0 <= probability <= 1:
                    response.failure("Некорректная вероятность")
                elif not model_version:
                    response.failure("Отсутствует версия модели")
                else:
                    response.success()

            except (ValueError, KeyError, TypeError) as exc:
                response.failure(f"Некорректный ответ API: {exc}")
