#!/usr/bin/env python3
import typing as T
import warnings

class E0D0Context(object):
    def __init__(self, sync: int = 0xe0, esc: int = 0xd0) -> None:
        self.sync = sync
        self.esc = esc
        self.decoder_is_escaping = False
        self.encoder_is_in_transaction = False

    def reset(self):
        '''Reset the encoder and decoder context'''
        self.reset_decoder()
        self.reset_encoder()

    def reset_decoder(self):
        self.decoder_is_escaping = False

    def reset_encoder(self):
        self.encoder_is_in_transaction = False

    def encode(self, data: bytes) -> bytes:
        result = bytearray()
        if not self.encoder_is_in_transaction:
            result.append(self.sync)
            self.encoder_is_in_transaction = True
        for b in data:
            if b in (self.sync, self.esc):
                result.append(self.esc)
                result.append((b-1) & 0xff)
            else:
                result.append(b)
        return bytes(result)

    def finalize(self, data: bytes) -> bytes:
        result = self.encode(data)
        self.encoder_is_in_transaction = False
        return result

    def decode(self, data: bytes) -> T.Tuple[bytes]:
        result = list()
        decoded_cur = bytearray()
        if len(data) == 0:
            return tuple()

        for b in data:
            if b == self.sync:
                if self.decoder_is_escaping:
                    warnings.warn('Sync received after escape. Escape dropped.')
                self.reset_decoder()
                # Next packet
                # In case of spamming sync, only one empty packet will be returned
                if len(decoded_cur) != 0:
                    result.append(bytes(decoded_cur))
                    decoded_cur = bytearray()
            elif b == self.esc:
                if self.decoder_is_escaping:
                    warnings.warn('Escape received after escape. Will ignore the new escape byte.')
                else:
                    self.decoder_is_escaping = True
            elif self.decoder_is_escaping:
                decoded_cur.append((b+1) & 0xff)
                self.decoder_is_escaping = False
            else:
                decoded_cur.append(b)
        result.append(bytes(decoded_cur))
        return tuple(result)

