import unittest
from unittest.mock import patch

from realme_buds.bluez import BATTERY_INTERFACE, DEVICE_INTERFACE, Device, connected_devices, select_device


OBJECTS = {
    "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01": {
        DEVICE_INTERFACE: {
            "Address": "AA:BB:CC:DD:EE:01",
            "Name": "Laptop",
            "Connected": True,
            "UUIDs": ["0000110b-0000-1000-8000-00805f9b34fb"],
        }
    },
    "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_02": {
        DEVICE_INTERFACE: {
            "Address": "AA:BB:CC:DD:EE:02",
            "Name": "realme Buds T310",
            "Connected": True,
            "UUIDs": ["0000079A-D102-11E1-9B23-00025B00A5A5"],
            "Modalias": "bluetooth:v02B0p0000d001F",
            "ServicesResolved": True,
        },
        BATTERY_INTERFACE: {"Percentage": 80},
    },
    "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_03": {
        DEVICE_INTERFACE: {
            "Address": "AA:BB:CC:DD:EE:03",
            "Alias": "realme Buds Wireless",
            "Connected": False,
            "UUIDs": ["00001107-d102-11e1-9b23-00025b00a5a5"],
        }
    },
}


class BluezTests(unittest.TestCase):
    def test_realme_name_with_known_opo_service_is_recognised_experimental_candidate(self):
        t310 = Device(
            address="AA:BB:CC:DD:EE:06",
            name="realme Buds T310",
            connected=True,
            uuids=("0000079a-d102-11e1-9b23-00025b00a5a5",),
            battery=None,
        )
        self.assertTrue(t310.looks_compatible)

    def test_realme_air_name_with_known_service_is_recognised_candidate(self):
        air = Device(
            address="AA:BB:CC:DD:EE:05",
            name="realme Buds Air 6",
            connected=True,
            uuids=("0000079a-d102-11e1-9b23-00025b00a5a5",),
            battery=None,
        )
        self.assertTrue(air.looks_compatible)

    def test_brand_name_without_known_service_is_not_recognised(self):
        device = Device(
            address="AA:BB:CC:DD:EE:05",
            name="realme audio device",
            connected=True,
            uuids=("0000110b-0000-1000-8000-00805f9b34fb",),
            battery=None,
        )
        self.assertFalse(device.looks_compatible)

    @patch("realme_buds.bluez._managed_objects", return_value=OBJECTS)
    def test_connected_devices_uses_object_manager_snapshot(self, managed_objects):
        devices = connected_devices()
        self.assertEqual(len(devices), 2)
        buds = devices[1]
        self.assertEqual(buds.name, "realme Buds T310")
        self.assertEqual(buds.battery, 80)
        self.assertEqual(buds.modalias, "bluetooth:v02B0p0000d001F")
        self.assertTrue(buds.services_resolved)
        self.assertTrue(buds.looks_compatible)
        managed_objects.assert_called_once_with()

    @patch("realme_buds.bluez._managed_objects", return_value=OBJECTS)
    def test_explicit_selection_is_case_insensitive(self, _managed_objects):
        self.assertEqual(select_device("aa:bb:cc:dd:ee:02").name, "realme Buds T310")

    @patch("realme_buds.bluez._managed_objects")
    def test_ambiguous_automatic_selection_fails(self, managed_objects):
        second = dict(OBJECTS)
        second["/org/bluez/hci0/dev_AA_BB_CC_DD_EE_04"] = {
            DEVICE_INTERFACE: {
                "Address": "AA:BB:CC:DD:EE:04",
                "Name": "realme Buds Air",
                "Connected": True,
                "UUIDs": ["00001107-d102-11e1-9b23-00025b00a5a5"],
            }
        }
        managed_objects.return_value = second
        with self.assertRaisesRegex(RuntimeError, "--device"):
            select_device()


if __name__ == "__main__":
    unittest.main()
