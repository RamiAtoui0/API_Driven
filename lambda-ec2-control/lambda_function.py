import json
import boto3
import os

def lambda_handler(event, context):
    # In LocalStack, don't specify endpoint_url
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # Get instance ID from environment variable
    instance_id = os.environ.get('INSTANCE_ID')
    
    # Parse the event - API Gateway wraps the body in a 'body' field
    print(f"Received event: {json.dumps(event)}")
    
    if 'body' in event:
        # Request came from API Gateway
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    else:
        # Direct Lambda invocation
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
            # Get instance status
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
