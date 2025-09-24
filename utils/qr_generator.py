import io
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from aiogram.types import BufferedInputFile


def generate_qr_code(data: str) -> BufferedInputFile:
    """Генерация QR-кода для конфигурации"""
    
    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    qr.add_data(data)
    qr.make(fit=True)
    
    # Создаем изображение с rounded стилем
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        fill_color="black",
        back_color="white"
    )
    
    # Конвертируем в байты
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    
    return BufferedInputFile(
        bio.read(),
        filename="config_qr.png"
    )