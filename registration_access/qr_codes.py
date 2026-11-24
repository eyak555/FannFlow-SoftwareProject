import base64
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage


def qr_code_data_uri(value):
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    encoded_svg = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"
