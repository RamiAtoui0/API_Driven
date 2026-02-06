# ATELIER API-DRIVEN INFRASTRUCTURE

## Description

Ce projet met en place une architecture API-driven permettant de contrôler des instances EC2 via des requetes HTTP. L'infrastructure utilise API Gateway et AWS Lambda pour orchestrer des actions sur des instances EC2 dans un environnement AWS simule avec LocalStack, execute dans GitHub Codespaces.

## Architecture

L'architecture se compose de quatre elements principaux :

1. Client HTTP : Envoie des requetes POST avec des actions (start, stop, status)
2. API Gateway : Recoit les requetes HTTP et les transmet a Lambda
3. Fonction Lambda : Execute le code Python pour controler l'instance EC2
4. Instance EC2 : L'instance cible qui peut etre demarree ou arretee

Le tout fonctionne dans LocalStack, un emulateur AWS local qui simule les services AWS sans avoir besoin d'un compte AWS reel.

## Installation

### Etape 1 : Creer un Codespace

Depuis le repository GitHub, cliquez sur Code puis Codespaces et creez un nouveau Codespace.

### Etape 2 : Installer LocalStack

Dans le terminal du Codespace, executez les commandes suivantes :
```
sudo mkdir -p /rep_localstack
sudo python3 -m venv ./rep_localstack
sudo pip install --upgrade pip && python3 -m pip install localstack
localstack start -d
```

Verifiez que LocalStack fonctionne :
```
localstack status services
```

### Etape 3 : Installer AWS CLI
```
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

### Etape 4 : Configurer AWS CLI
```
export AWS_ENDPOINT="http://localhost:4566"
aws configure set aws_access_key_id test
aws configure set aws_secret_access_key test
aws configure set region us-east-1
```

### Etape 5 : Creer l'instance EC2
```
aws ec2 run-instances \
  --image-id ami-ff0fea8310f3 \
  --count 1 \
  --instance-type t2.micro \
  --endpoint-url=$AWS_ENDPOINT
```

Recuperez l'ID de l'instance :
```
INSTANCE_ID=$(aws ec2 describe-instances \
  --endpoint-url=$AWS_ENDPOINT \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)
echo $INSTANCE_ID
```

### Etape 6 : Creer la fonction Lambda

Creez le repertoire et le fichier Python :
```
mkdir lambda-ec2-control
cd lambda-ec2-control
```

Creez le fichier lambda_function.py avec le contenu suivant :
```python
import json
import boto3
import os

def lambda_handler(event, context):
    ec2 = boto3.client('ec2', region_name='us-east-1')
    instance_id = os.environ.get('INSTANCE_ID')
    
    if 'body' in event:
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    else:
        body = event
    
    action = body.get('action', 'status')
    
    try:
        if action == 'start':
            ec2.start_instances(InstanceIds=[instance_id])
            message = f'Starting instance {instance_id}'
        elif action == 'stop':
            ec2.stop_instances(InstanceIds=[instance_id])
            message = f'Stopping instance {instance_id}'
        else:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            state = response['Reservations'][0]['Instances'][0]['State']['Name']
            message = f'Instance {instance_id} is {state}'
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': message,
                'instance_id': instance_id
            })
        }
    except Exception as e:
        import traceback
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'trace': traceback.format_exc()
            })
        }
```

Installez les dependances et creez le package :
```
pip install boto3 -t .
zip -r lambda_function.zip .
cd ..
```

Creez le role IAM :
```
cat > trust-policy.json << 'POLICY'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
POLICY

aws iam create-role \
  --role-name lambda-ec2-role \
  --assume-role-policy-document file://trust-policy.json \
  --endpoint-url=$AWS_ENDPOINT
```

Creez la fonction Lambda :
```
aws lambda create-function \
  --function-name ec2-control \
  --runtime python3.9 \
  --role arn:aws:iam::000000000000:role/lambda-ec2-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda-ec2-control/lambda_function.zip \
  --environment Variables="{INSTANCE_ID=$INSTANCE_ID}" \
  --timeout 30 \
  --endpoint-url=$AWS_ENDPOINT
```

### Etape 7 : Creer l'API Gateway

Creez l'API REST :
```
API_ID=$(aws apigateway create-rest-api \
  --name 'EC2-Control-API' \
  --description 'API to control EC2 instances' \
  --endpoint-url=$AWS_ENDPOINT \
  --query 'id' \
  --output text)

ROOT_RESOURCE_ID=$(aws apigateway get-resources \
  --rest-api-id $API_ID \
  --endpoint-url=$AWS_ENDPOINT \
  --query 'items[0].id' \
  --output text)

RESOURCE_ID=$(aws apigateway create-resource \
  --rest-api-id $API_ID \
  --parent-id $ROOT_RESOURCE_ID \
  --path-part ec2 \
  --endpoint-url=$AWS_ENDPOINT \
  --query 'id' \
  --output text)
```

Configurez la methode POST :
```
aws apigateway put-method \
  --rest-api-id $API_ID \
  --resource-id $RESOURCE_ID \
  --http-method POST \
  --authorization-type NONE \
  --endpoint-url=$AWS_ENDPOINT

aws apigateway put-integration \
  --rest-api-id $API_ID \
  --resource-id $RESOURCE_ID \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:000000000000:function:ec2-control/invocations" \
  --endpoint-url=$AWS_ENDPOINT

aws lambda add-permission \
  --function-name ec2-control \
  --statement-id apigateway-access \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --endpoint-url=$AWS_ENDPOINT

aws apigateway create-deployment \
  --rest-api-id $API_ID \
  --stage-name prod \
  --endpoint-url=$AWS_ENDPOINT
```

### Etape 8 : Rendre l'API accessible publiquement

Dans le Codespace, allez dans l'onglet PORTS en bas de l'ecran. Trouvez le port 4566, faites un clic droit et selectionnez Port Visibility puis Public. Copiez l'URL du port 4566.

## Utilisation

### URL de l'API

L'URL locale de l'API est :
```
http://localhost:4566/restapis/{API_ID}/prod/_user_request_/ec2
```

L'URL publique est :
```
https://{CODESPACE_URL}-4566.app.github.dev/restapis/{API_ID}/prod/_user_request_/ec2
```

### Actions disponibles

Verifier le statut de l'instance :
```
curl -X POST {API_URL} \
  -H "Content-Type: application/json" \
  -d '{"action": "status"}'
```

Arreter l'instance :
```
curl -X POST {API_URL} \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
```

Demarrer l'instance :
```
curl -X POST {API_URL} \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

## Tests

Pour verifier que LocalStack fonctionne correctement :
```
curl https://{CODESPACE_URL}-4566.app.github.dev/_localstack/health
```

Pour tester la fonction Lambda directement :
```
aws lambda invoke \
  --function-name ec2-control \
  --cli-binary-format raw-in-base64-out \
  --payload '{"action": "status"}' \
  --endpoint-url=$AWS_ENDPOINT \
  response.json

cat response.json
```

## Structure du projet
```
API_Driven/
├── README.md
├── lambda-ec2-control/
│   ├── lambda_function.py
│   └── lambda_function.zip
├── trust-policy.json
└── API_Driven.png
```

## Informations techniques

Instance EC2 ID : i-d0ff866bbb1983192
Lambda Function : ec2-control
API Gateway ID : koqq1j5tet
Region : us-east-1
LocalStack Version : 4.13.2.dev30


## Auteur

Rami Atoui
