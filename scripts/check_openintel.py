"""Check openintel ingestor and czds ingestor logs"""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("158.69.211.109", username="ubuntu", password="mls1509ti", timeout=20)

def run(cmd, timeout=15):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode() + stderr.read().decode()

print("=== openintel_ingestor logs (last 50 lines) ===")
print(run("docker service logs observador_openintel_ingestor --tail 50 --no-trunc 2>&1"))

print("\n=== openintel_ingestor container inspect (task history) ===")
print(run("docker service ps observador_openintel_ingestor --no-trunc 2>&1"))

client.close()
