import requests

url = "https://api.etherscan.io/v2/api?module=proxy&action=eth_getTransactionByHash&apikey=Z7JQRN2EP5SITUXU7CTPAZEHZ51U19E4J2"

response = requests.get(url)

print(response.text)