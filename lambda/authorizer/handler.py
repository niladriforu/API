import json
import os
import jwt
from datetime import datetime, timedelta


def get_secret_key():
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise ValueError(
            "JWT_SECRET_KEY is not set. "
            "Set it as a Lambda environment variable, or export it locally for testing."
        )
    return secret

def lambda_handler(event, context):
    """
    Custom Lambda authorizer that validates tokens.
    
    Event structure:
    {
        "type": "TOKEN",
        "authorizationToken": "Bearer <token>",
        "methodArn": "arn:aws:execute-api:region:account-id:api-id/stage/method/resource-path"
    }
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract the token from the authorization header
        token = event.get('authorizationToken', '')
        
        # Remove "Bearer " prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Verify the token
        payload = verify_token(token)
        
        # Extract the method ARN
        method_arn = event['methodArn']
        
        # If token is valid, generate an IAM policy allowing the request
        policy = generate_policy(
            principal_id=payload.get('user_id', 'user'),
            effect='Allow',
            resource=method_arn,
            payload=payload
        )
        
        print(f"Authorization successful for user: {payload.get('user_id')}")
        return policy
        
    except Exception as e:
        print(f"Authorization failed: {str(e)}")
        raise Exception('Unauthorized')


def verify_token(token):
    """
    Verify the JWT token and return the payload.
    Raises an exception if token is invalid or expired.
    """
    try:
        # Decode and verify the JWT token
        payload = jwt.decode(token, get_secret_key(), algorithms=['HS256'])
        print(f'payload is {payload}')
        
        # Additional validation: check expiration
        if 'exp' in payload:
            exp_timestamp = payload['exp']
            if datetime.fromtimestamp(exp_timestamp) < datetime.now():
                raise Exception('Token has expired')
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise Exception('Token has expired')
    except jwt.InvalidTokenError:
        raise Exception('Invalid token')
    except Exception as e:
        raise Exception(f'Token validation failed: {str(e)}')


def generate_policy(principal_id, effect, resource, payload=None):
    """
    Generate an IAM policy that allows or denies access to AWS API Gateway resources.
    
    Args:
        principal_id: The principal user identification associated with the token
        effect: 'Allow' or 'Deny'
        resource: The ARN of the API Gateway resource
        payload: Custom context data to pass to the Lambda function
    
    Returns:
        A policy dictionary that controls access
    """
    
    auth_response = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    }
    
    # Add custom context data that will be passed to the Lambda function
    if payload:
        auth_response['context'] = {
            'user_id': payload.get('user_id', ''),
            'email': payload.get('email', ''),
            'role': payload.get('role', 'user')
        }
    
    return auth_response


# Helper function to generate test tokens (for learning purposes)
def generate_test_token(user_id, email='test@example.com', role='user', expires_in_hours=24):
    """
    Generate a JWT token for testing.
    Run this separately to create valid tokens.
    """
    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=expires_in_hours)
    }
    
    token = jwt.encode(payload, get_secret_key(), algorithm='HS256')
    return token


# Test the authorizer locally
if __name__ == '__main__':
    # Generate a test token
    test_token = generate_test_token('niladriforu', 'niladriforu@gmail.com', 'admin')
    print(f"Generated test token: {test_token}\n")
    
    # Simulate an API Gateway event
    test_event = {
        'type': 'TOKEN',
        'authorizationToken': f'Bearer {test_token}',
        'methodArn': 'arn:aws:execute-api:us-east-1:123456789:myapi/prod/GET/users'
    }
    
    # Test the authorizer
    result = lambda_handler(test_event, None)
    print(f"Authorization result: {json.dumps(result, indent=2)}")