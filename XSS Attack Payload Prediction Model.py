#!/usr/bin/env python
# coding: utf-8

# ## Create a S3 bucket

# In[13]:


import boto3
from botocore.exceptions import ClientError

bucket_name = 'autopentest-sagemaker'

s3 = boto3.resource('s3')
try:
    s3.create_bucket(Bucket = bucket_name, CreateBucketConfiguration={'LocationConstraint': 'ap-southeast-2'})
    print('S3 bucket created successfully!')
except Exception as e:
    print('S3 error: ', e)


# In[14]:


# Set an output path where the trained model will be saved
prefix = 'xss-xgboost-algo-model'
output_path = 's3://{}/{}/output'.format(bucket_name, prefix)
print(output_path)


# ## Upload datasets to S3 bucket

# In[15]:


# Download the XSS datasets file and load them into Pandas dataframe
import pandas as pd

try:
    train_data = pd.read_csv('XSSTraining.csv', engine = 'python', header = 0, sep = ',')
    print('Success: Training Data loaded into dataframe')
except Exception as e:
    print('Data load error: ', e)

try:
    test_data = pd.read_csv('XSSTesting.csv', engine = 'python', header = 0, sep = ',')
    print('Success: Testing Data loaded into dataframe')
except Exception as e:
    print('Data load error: ', e)


# In[16]:


print(train_data)


# In[17]:


# Pre-process the data before put into S3 bucket
import os
import sagemaker
from sagemaker.session import TrainingInput, Session

# The independent attribute, which is 'Class' here, should be in the first column
# Train_data into the bucket
pd.concat([train_data['Class'], train_data.drop(['Class'], axis = 1)], axis = 1).to_csv('train.csv', index = False, header = False)
boto3.Session().resource('s3').Bucket(bucket_name).Object(os.path.join(prefix, 'train/train.csv')).upload_file('train.csv')

# SageMaker accesses the training data path in S3
s3_input_train = sagemaker.TrainingInput(s3_data = 's3://{}/{}/train'.format(bucket_name, prefix), content_type = 'csv')


# In[18]:


import numpy as np

# Same thing with the testing data
pd.concat([test_data['Class'], test_data.drop(['Class'], axis = 1)], axis = 1)

# But we are going to split testing datasets into two files as it's too big too process
test_data_1, test_data_2 = np.split(test_data.sample(frac = 1, random_state = 1729), [int(0.5 * len(test_data))])
test_data_1.to_csv('test1.csv', index = False, header = False)
test_data_2.to_csv('test2.csv', index = False, header = False)
                                                                                      
boto3.Session().resource('s3').Bucket(bucket_name).Object(os.path.join(prefix, 'test/test1.csv')).upload_file('test1.csv')
boto3.Session().resource('s3').Bucket(bucket_name).Object(os.path.join(prefix, 'test/test2.csv')).upload_file('test2.csv')

# SageMaker accesses the testing data path in S3
s3_input_test = sagemaker.TrainingInput(s3_data = 's3://{}/{}/test'.format(bucket_name, prefix), content_type = 'csv')


# ## Build XGboost model

# In[19]:


from sagemaker.amazon.amazon_estimator import image_uris

# Get XGboost image and put it into a container
XGBOOST_container = image_uris.retrieve(region = boto3.Session().region_name, framework = 'xgboost', version = '1.0-1')

# Initialise hyperparameters
hyperparameters = {
        "max_depth": "5",
        "eta": "0.2",
        "gamma": "4",
        "min_child_weight": "6",
        "subsample": "0.7",
        "objective": "binary:logistic",
        "num_round": "10"
        }

# Construct an estimator that calls the xgboost container
estimator = sagemaker.estimator.Estimator(
    image_uri = XGBOOST_container,
    hyperparameters = hyperparameters,
    role = sagemaker.get_execution_role(),
    instance_count = 1,
    instance_type = 'ml.c5.xlarge',
    volume_size = 20,
    output_path = output_path,
    use_spot_instances = True,
    max_run = 300,
    max_wait = 600
)


# In[20]:


estimator.fit({'train': s3_input_train, 'validation': s3_input_test})


# In[21]:


xgb_predictor = estimator.deploy(initial_instance_count = 1, instance_type = 'ml.c5.xlarge')


# ## Prediction of the testing data

# In[22]:


from sagemaker.predictor import CSVSerializer

test_data_1_array = test_data_1.drop(['Class'], axis = 1).values # Load the data into ana array
xgb_predictor.serializer = sagemaker.serializers.CSVSerializer()  # Set the serializer type

response = xgb_predictor.predict(test_data_1_array).decode('utf-8')
predictions = np.fromstring(response[1:], sep = ',')   # Turn the predition into an array
print(predictions.shape)


# In[25]:


## Display the prediction results
cm = pd.crosstab(index=test_data_1['Class'], columns=np.round(predictions), rownames=['Actual'], colnames=['Predicted'])
tn = cm.iloc[0,0]; fn = cm.iloc[1,0]; tp = cm.iloc[1,1]; fp = cm.iloc[0,1]; p = (tp+tn)/(tp+tn+fp+fn)*100
print("\n{0:<20}{1:<4.1f}%\n".format("Overall Classification Rate: ", p))
print("{0:<15}{1:<15}{2:>8}".format("Predicted", "Benign", "Malicious"))
print("Actual")
print("{0:<15}{1:<2.0f}% ({2:<}){3:>6.0f}% ({4:<})".format("Benign", tn/(tn+fn)*100, tn, fp/(tp+fp)*100, fp))
print("{0:<16}{1:<1.0f}% ({2:<}){3:>7.0f}% ({4:<}) \n".format("Malicious", fn/(tn+fn)*100, fn, tp/(tp+fp)*100, tp))


# In[ ]:




