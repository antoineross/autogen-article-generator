FROM python:3.11

# Create a non-root user with home directory
RUN useradd -m -u 1000 user

# Set user and environment variables
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set the working directory in the container
WORKDIR $HOME/app

# Copy the requirements.txt file to the container
COPY requirements.txt $HOME/app/

# Install Python dependencies from requirements.txt
RUN pip install --user -r $HOME/app/requirements.txt

# Copy the application files, including app.py
COPY --chown=user:user . $HOME/app/

# Ensure user has write permission to the app directory
USER root
RUN chown -R user:user $HOME/app
USER user

# Specify the command to run your application
CMD ["chainlit", "run", "app.py", "--port", "7860"]
