#!/usr/bin/env python3

import asyncio
from segaslider.app import SegaSliderApp

if __name__ == '__main__':
    asyncio.run(SegaSliderApp().async_run('asyncio'))
