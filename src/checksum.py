#!/usr/bin/env python3
import typing as T

class BaseJVSChecksum(object):
    def __init__(self, init: int = 0) -> None:
        self.init = init & 0xff
        self.state = self.init

    def reset(self):
        self.state = self.init

    def getvalue(self) -> int:
        return self.state

    def update(self, data: bytes) -> None:
        raise NotImplemented()

class JVSChecksum(BaseJVSChecksum):
    def update(self, data: bytes) -> None:
        self.state += sum(data)
        self.state &= 0xff

class NegativeJVSChecksum(BaseJVSChecksum):
    def update(self, data: bytes) -> None:
        self.state -= sum(data)
        self.state &= 0xff
