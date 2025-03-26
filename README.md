# Video Engineering test

1. A python script to interact with the AWS Media Services API and create a MediaLive RTMP Input.
AWS, AWS_VPC and ON_PREMISES source types are supported:
./rtmp_quick.py --source-type AWS --name aws_2 --app-name live --app-instance stream1  --security-group 10.10.10.11/32
./rtmp_quick.py --source-type AWS_VPC --name vpc-input1 --app-name live --app-instance stream1 --subnets subnet-49d65405 subnet-1138d57a  --security-group sg-f25d8d96  --role-arn arn:aws:iam::289306338XXX:role/MediaLiveAccessRole
./rtmp_quick.py --source-type ON_PREMISES --name onprem-input --app-name live --app-instance stream1 --network 3878051
Most simple RTMP push input generation method, given that on_prem.json is properly setup:
./rtmp_quick.py --config on_prem.json
Based on RTMP push MediaLive input setup https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/medialive/client/create_input.html


2. FFmpeg command to take a 4:3 aspect video and add letterbars to make it 16:9.

Quickest path to generate padded video output:
`ffmpeg -i aspect43.mp4 -vf "pad=ih*16/9:ih:(ow-iw)/2,setdar=16/9" -acodec copy -vcodec libx264 -profile:v high -crf 7 aspect169.mp4`

pad filter takes standard values pad=width:height:x:y
width="ih=16/9" takes input hight and multiplies by 16, then dvides by 9, making it poper width of an output file when going from 4:3 to 16:9.
height="ih" stays the same, output 16:9 file with the side bars has the same width as the source 4:3 file.
x="(ow-iw)/2" moves the video's top left corner (x,y) position to the differnce bwetween input width and output width divided by two = exatly one bar.
"y" is NULL, as height stays the same.
"setdar=16/9" - sets display aspect ratio to 16:9.
"acodec copy" passes through elemental audio from source mix to the encoded output.
"-vcodec libx264 -profile:v high -crf 7" are encoding parameters, use: h264 encoder,  high proifle (higher compression rate), and high constant quality that is nearly lossless for postprod user gen content use. For tier 1 it'd be MPEG2 or Apple ProRes normally. Also padding of a VOD asset would normally involve a FFprobe an Media Info parsing of a file, then based on tech metadata analysis generate a filter chain based on each frame analysis (inverse telecine, deinteralce, fps, resolution, pad, crop, volumenorm and other filters as needed). But that wouldn't be one command )

3. Create an architecture diagram showing the main blocks involved in live streaming, starting from the live event site, ending at the end user.
test_diagram_basic_layout3.pdf
Top level diagram of all main items for live public CDNs RTMP, private CDN HLS/DASH, Sat and Cable distribution. page 1.
Top level diagram of basic OTT AWS setup. page 2.

Thanks!
