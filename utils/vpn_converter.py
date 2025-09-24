import struct
import zlib
import base64
import socket
import ipaddress
import re

def qCompress(data, level=-1):
    compressed = zlib.compress(data, level)
    header = struct.pack('>I', len(data))
    return header + compressed

def base64url_encode(data):
    encoded = base64.urlsafe_b64encode(data)
    return encoded.rstrip(b'=')

def is_ip_address(address):
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

def resolve_dns_to_ip(dns_name):
    try:
        ip_address = socket.gethostbyname(dns_name)
        return ip_address
    except socket.gaierror:
        return None

def process_conf_data(data):
    """Обрабатывает конфигурационные данные, заменяя DNS на IP"""
    def replace_endpoint(match):
        full_line = match.group(0)
        prefix = match.group(1)
        address = match.group(2)
        port = match.group(3)
        suffix = match.group(4)
        
        if not is_ip_address(address):
            resolved_ip = resolve_dns_to_ip(address)
            if resolved_ip:
                return f"{prefix}{resolved_ip}:{port}{suffix}"
            else:
                # Если не удалось разрешить DNS, оставляем как есть
                return full_line
        else:
            return full_line
    
    pattern = r'^(.*Endpoint\s*=\s*)([^\s:]+)(?::(\d+))(.*)$'
    return re.sub(pattern, replace_endpoint, data, flags=re.MULTILINE)

def conf_to_vpn_url(conf_data: str) -> str:
    """Конвертирует .conf конфигурацию в vpn:// формат"""
    try:
        processed_data = process_conf_data(conf_data)
        data_bytes = processed_data.encode('utf-8')
        compressed = qCompress(data_bytes, level=8)
        base64_encoded = base64url_encode(compressed)
        return 'vpn://' + base64_encoded.decode('ascii')
    except Exception as e:
        raise Exception(f"Ошибка при конвертации в vpn:// формат: {e}")