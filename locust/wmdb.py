from locust import HttpUser, between, task


class WmdbLocust(HttpUser):
    wait_time = between(300, 360)

    def on_start(self):
        self.client.headers = {"Content-Type": "application/vnd.api+json"}
        with self.client.post(
            "/token/login/",
            json={
                "data": {
                    "type": "ObtainJSONWebToken",
                    "id": None,
                    "attributes": {"username": "rlcs", "password": "teste2019"},
                }
            },
            name="Login",
        ) as response:
            data = response.json()
            token = data["data"]["token"]

            self.client.headers = {"Authorization": f"JWT {token}"}

    @task
    def first_sync(self):
        url = (
            "/WmDBSync/?page=1&lastPulledAt=0&schemaVersion=2&"
            "company=433c0cd2-80e2-46c9-b8c5-030fc61070e5"
        )
        while url:
            with self.client.get(url, name="WmDBSync") as response:
                try:
                    data = response.json()
                    url = data.get("next_page")
                except Exception:
                    pass
