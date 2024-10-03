how to test a POST endpoint with a payload:


```
# URL
http://127.0.0.1:8000/<Endpoint Name>


# Body
{
  "files": [
    "http://arxiv.org/pdf/1706.03762",
    "http://example.com/anotherfile.pdf"
  ]
}
```