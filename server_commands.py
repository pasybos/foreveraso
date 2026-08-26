import paramiko
import re
from config import SSH_HOST, SSH_PORT, SSH_USERNAME, SSH_PASSWORD, INBOUND_ID

class ServerCommands:
    def __init__(self):
        self.client = None
    
    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(SSH_HOST, port=SSH_PORT, username=SSH_USERNAME, password=SSH_PASSWORD)
    
    def disconnect(self):
        if self.client:
            self.client.close()
    
    def create_client(self, email, expiry_timestamp, total_gb=0, limit_ip=1):
        """
        Создаёт клиента в инбаунде через команду x-ui
        """
        self.connect()
        # Команда для добавления клиента
        # x-ui api add-client --inbound-id ID --email email --expiry TIMESTAMP --total GB --limit IP
        cmd = f"x-ui api add-client --inbound-id {INBOUND_ID} --email {email} --expiry {expiry_timestamp} --total {total_gb} --limit {limit_ip}"
        stdin, stdout, stderr = self.client.exec_command(cmd)
        output = stdout.read().decode()
        error = stderr.read().decode()
        self.disconnect()
        
        if error:
            raise Exception(f"Ошибка создания клиента: {error}")
        
        # Ищем ID клиента в выводе
        # Обычно x-ui выводит UUID или ID
        # Попробуем найти ссылку vless://
        # Если не получается, можно получить ссылку отдельной командой
        # Но пока просто вернём вывод
        return output
    
    def get_client_link(self, client_id):
        # Можно получить ссылку через x-ui api get-client-link
        pass
