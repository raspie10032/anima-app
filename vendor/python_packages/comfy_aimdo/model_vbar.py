"""Model VBAR fallback for the GemmAnima no-aimdo shim."""


class ModelVBAR:
    def __init__(self, size, device):
        self._size = int(size)
        self.device = device

    def prioritize(self):
        return None

    def deprioritize(self):
        return None

    def alloc(self, size):
        return None

    def loaded_size(self):
        return 0

    def set_watermark_limit(self, size_bytes):
        return None

    def free_memory(self, size_bytes):
        return 0

    def nr_pages(self):
        return 0

    def watermark(self):
        return 0

    def residency(self):
        return []


def vbars_analyze():
    return 0


def vbar_fault(alloc):
    return None


def vbar_unpin(alloc):
    return None


def vbar_signature_compare(a, b):
    return False
