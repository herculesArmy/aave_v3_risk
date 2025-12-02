import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Query to get schema information
introspection_query = """
{
  __type(name: "UserReserve") {
    name
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""

response = requests.post(
    os.getenv('SUBGRAPH_URL'),
    json={'query': introspection_query},
    headers={'Content-Type': 'application/json'}
)

data = response.json()
print("=== UserReserve Fields ===")
print(json.dumps(data, indent=2))

# Also check Reserve fields
reserve_query = """
{
  __type(name: "Reserve") {
    name
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""

response2 = requests.post(
    os.getenv('SUBGRAPH_URL'),
    json={'query': reserve_query},
    headers={'Content-Type': 'application/json'}
)

data2 = response2.json()
print("\n\n=== Reserve Fields ===")
print(json.dumps(data2, indent=2))

# Check User fields
user_query = """
{
  __type(name: "User") {
    name
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""

response3 = requests.post(
    os.getenv('SUBGRAPH_URL'),
    json={'query': user_query},
    headers={'Content-Type': 'application/json'}
)

data3 = response3.json()
print("\n\n=== User Fields ===")
print(json.dumps(data3, indent=2))
