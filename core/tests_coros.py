import json
from unittest.mock import patch

from django.test import TestCase

from core.models import CorosWorkoutPush


class CorosApplicationEndpointTests(TestCase):
    def test_status_endpoint_is_public_and_healthy(self):
        response = self.client.get("/integrations/coros/status/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch.dict("os.environ", {"COROS_PUSH_CLIENT": "mila-client", "COROS_PUSH_SECRET": "mila-secret"})
    def test_authenticated_push_returns_required_coros_result(self):
        response = self.client.post(
            "/integrations/coros/workouts/",
            data=json.dumps({"sportDataList": [{"labelId": 123}]}),
            content_type="application/json",
            headers={"client": "mila-client", "secret": "mila-secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "ok", "result": "0000"})
        self.assertEqual(CorosWorkoutPush.objects.count(), 1)

    @patch.dict("os.environ", {"COROS_PUSH_CLIENT": "mila-client", "COROS_PUSH_SECRET": "mila-secret"})
    def test_duplicate_push_is_accepted_without_duplicate_storage(self):
        kwargs = {
            "data": json.dumps({"sportDataList": [{"labelId": 123}]}),
            "content_type": "application/json",
            "headers": {"client": "mila-client", "secret": "mila-secret"},
        }
        first = self.client.post("/integrations/coros/workouts/", **kwargs)
        second = self.client.post("/integrations/coros/workouts/", **kwargs)

        self.assertEqual(first.json()["result"], "0000")
        self.assertEqual(second.json()["result"], "0000")
        self.assertEqual(CorosWorkoutPush.objects.count(), 1)

    @patch.dict("os.environ", {"COROS_PUSH_CLIENT": "mila-client", "COROS_PUSH_SECRET": "mila-secret"})
    def test_push_rejects_invalid_credentials(self):
        response = self.client.post(
            "/integrations/coros/workouts/",
            data="{}",
            content_type="application/json",
            headers={"client": "wrong", "secret": "wrong"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(response.json()["result"], "0000")
        self.assertFalse(CorosWorkoutPush.objects.exists())
