# Video Engineering test

## AWS MediaLive input script
A python script to interact with the AWS Media Services API and create a new MediaLive RTMP Input.
All three source types are supported. Best way to lookup input specs would be to visit AWS MediaLive web console and setup ML_networks, ML_Securuity_groups etc. Or use a CLI tool.


#### AWS ####
Lookup and setup system configuration specific to AWS source type.
```
# List existing MediaLive input security groups
aws medialive list-input-security-groups

# Create MediaLive security group with specific CIDR
aws medialive create-input-security-group --whitelist-rules Cidr=x.x.x.x/32
```

Launch AWS input setup:
```
./rtmp_quick.py --source-type AWS --name aws_2 --app-name live --app-instance stream1  --security-group 10.10.10.11/32
```  
  
#### AWS_VPC  ####
Lookup system configuration specific to AWS_VPC source type. To create new items needed by VPC setup some assistance from DEV OPS might be mandatory.
```
# List available subnets (need at least 2)
aws ec2 describe-subnets --query 'Subnets[*].{SubnetId:SubnetId,CIDR:CidrBlock,AZ:AvailabilityZone}' --output table

# List EC2 security groups
aws ec2 describe-security-groups --query 'SecurityGroups[*].{ID:GroupId,Name:GroupName}' --output table

# List IAM roles
aws iam list-roles --query 'Roles[*].{Name:RoleName,ARN:Arn}' --output table
```

Launch AWS_VPC input setup:
```
rtmp_quick.py --source-type AWS_VPC --name vpc-input1 --app-name live --app-instance stream1 --subnets subnet-49d65405 subnet-1138d57a  --security-group sg-f25d8d96  --role-arn arn:aws:iam::289306338XXX:role/MediaLiveAccessRole
```  
  
#### ON_PREMISES ####
Lookup and setup system configuration specific to ON_PREMISES source type.  
```
# List existing MediaLive networks
aws medialive list-networks

# Create new MediaLive network
aws medialive create-network --name mynetwork --ip-pools '[{"Cidr":"10.0.0.0/24"}]'
```

Launch ON_PREMISES input setup:  
```
rtmp_quick.py --source-type ON_PREMISES --name onprem-input --app-name live --app-instance stream1 --network 3878051
```  

#### JSON CONFIG ####
Most simple RTMP push input generation method, given that on_prem.json is properly setup:  
``` 
rtmp_quick.py --config on_prem.json
```

Code is based on RTMP push MediaLive input setup https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/medialive/client/create_input.html

A more sophisticated and easier to use script is "rtmp_new_input.py" can generate new ML_network, ML_security_group, and select existing SecurityGroups and Subnets, but is a bit of bloatware.


## FFmpeg command 
Use FFmpeg to take a 4:3 aspect video and add letterbars to make it 16:9.

Quickest path to generate padded video output:
```
ffmpeg -i aspect43.mp4 -vf "pad=ih*16/9:ih:(ow-iw)/2,setdar=16/9" -acodec copy -vcodec libx264 -profile:v high -crf 7 aspect169.mp4
```

pad filter takes standard values pad=width:height:x:y  
**width="ih=16/9"** takes input height and multiplies by 16, then divides by 9, making it proper width of an output file when going from 4:3 to 16:9.  
**height="ih"** stays the same, output 16:9 file with the side bars has the same width as the source 4:3 file.  
**x="(ow-iw)/2"** shifts top left corner X position: input minus output widths divided by two = exactly one bar.  
**"y"** is NULL, as height stays the same.  
**"setdar=16/9"** - sets display aspect ratio to 16:9.  
**"acodec copy"** passes through elemental audio from source mix to the encoded output.  
**"vcodec libx264 profile:v high crf 7"** are encoding parameters, use: h264 encoder, high profile (higher compression rate), and decent video quality Constant Rate Factor of 7 (higher is lower quality) provides nearly lossless video compression at a manageable file size, far from Prores/Cineform.
Padding of a VOD media asset would normally involve FFprobe and MediaInfo parsing of a file, then based on tech metadata analysis generate a filter chain based on frame analysis, as this is not very reliable with every file type / use case. But that wouldn't be one command )


## Live event streaming diagram
Create an architecture diagram showing the main blocks involved in live streaming, starting from the live event site, ending at the end user.
**test_diagram_basic_layout3.pdf**
Top level diagram of all main items for live public CDNs RTMP, private CDN HLS/DASH, Sat and Cable distribution. page 1.
Top level diagram of basic OTT AWS setup. page 2.
  
    
Thanks!
