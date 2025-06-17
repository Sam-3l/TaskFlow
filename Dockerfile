# Use AWS's pre-built Python Lambda base image
FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies
RUN dnf install -y postgresql15-devel gcc python3-devel \
    && dnf clean all

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --ignore-installed -r requirements.txt

# Copy the entire project
COPY . .

# Remove the static directory
RUN rm -rf ./app/static

# Set the Lambda handler function (points to lambda_handler.handler)
CMD ["lambda_handler.handler"]