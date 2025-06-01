# Use AWS's pre-built Python Lambda base image
FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies (if needed, e.g., for psycopg2)
RUN yum install -y postgresql-devel gcc python3-devel \
    && yum clean all

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Set the Lambda handler function (points to lambda_handler.handler)
CMD ["lambda_handler.handler"]