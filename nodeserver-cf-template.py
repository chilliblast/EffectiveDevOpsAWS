"""Generating CloudFormation template."""

from ipaddress import ip_network
from ipify import get_ip

from troposphere import (
    autoscaling,
    Base64,
    cloudwatch,
    ec2,
    GetAtt,
    Join,
    Output,
    Parameter,
    Ref,
    Template,
    elasticloadbalancing as elb,
)

from troposphere.iam import (
    InstanceProfile,
    PolicyType as IAMPolicy,
    Role,
)

from troposphere.autoscaling import (
    AutoScalingGroup,
    LaunchConfiguration,
    ScalingPolicy,
)

from troposphere.cloudwatch import (
    Alarm,
    MetricDimension,
)

from awacs.aws import (
    Action,
    Allow,
    Policy,
    Principal,
    Statement,
)

from awacs.sts import AssumeRole

ApplicatioName = "nodeserver"
ApplicationPort = "3000"

GithubAccount = "chilliblast"
GithubAnsibleURL = "https://github.com/{}/ansible".format(GithubAccount)

AnsiblePullCmd = "/usr/local/bin/ansible-pull -U {} {}.yml -i localhost".format(GithubAnsibleURL,ApplicatioName)

myIP = str(ip_network(get_ip()))

AMI_image = "ami-e4515e0e"

t = Template()

t.add_description("Effective DevOps in AWS: HelloWorld web application")

t.add_parameter(Parameter(
    "KeyPair",
    Description="Name of an existing EC2 KeyPair to SSH",
    Type="AWS::EC2::KeyPair::KeyName",
    ConstraintDescription="must be the name of an existing EC2 KeyPair.",
))

t.add_parameter(Parameter( 
    "VpcId", 
    Type="AWS::EC2::VPC::Id", 
    Description="VPC" 
))

t.add_parameter(Parameter( 
    "PublicSubnet", 
    Description="PublicSubnet", 
    Type="List<AWS::EC2::Subnet::Id>", 
    ConstraintDescription="PublicSubnet" 
))

t.add_parameter(Parameter( 
    "ScaleCapacity", 
    Default="2", 
    Type="String", 
    Description="Number servers to run", 
))

t.add_parameter(Parameter( 
    'InstanceType', 
    Type='String', 
    Description='WebServer EC2 instance type', 
    Default='t2.micro', 
    AllowedValues=[ 
        't2.micro', 
        't2.small', 
        't2.medium', 
        't2.large', 
    ], 
    ConstraintDescription='must be a valid EC2 T2 instance type.', 
))

t.add_resource(ec2.SecurityGroup( 
    "LoadBalancerSecurityGroup", 
    GroupDescription="Web load balancer security group.", 
    VpcId=Ref("VpcId"),
    SecurityGroupIngress=[ 
        ec2.SecurityGroupRule( 
            IpProtocol="tcp", 
            FromPort="3000", 
            ToPort="3000", 
            CidrIp="0.0.0.0/0",
        ), 
    ], 
))

t.add_resource(elb.LoadBalancer( 
    "LoadBalancer", 
    Scheme="internet-facing",  
    Listeners=[ 
        elb.Listener( 
            LoadBalancerPort="3000", 
            InstancePort="3000", 
            Protocol="HTTP", 
            InstanceProtocol="HTTP" 
        ), 
    ], 
    HealthCheck=elb.HealthCheck( 
        Target="HTTP:3000/", 
        HealthyThreshold="5", 
        UnhealthyThreshold="2", 
        Interval="20", 
        Timeout="15", 
    ), 
    ConnectionDrainingPolicy=elb.ConnectionDrainingPolicy( 
        Enabled=True, 
        Timeout=10, 
    ),
    CrossZone=True,
    Subnets=Ref("PublicSubnet"), 
    SecurityGroups=[Ref("LoadBalancerSecurityGroup")], 
))

t.add_resource(ec2.SecurityGroup(
    "SecurityGroup",
    GroupDescription="Allow SSH and TCP/{} access".format(ApplicationPort),
    VpcId=Ref("VpcId"),
    SecurityGroupIngress=[
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort="22",
            ToPort="22",
            CidrIp=myIP,
        ),
        ec2.SecurityGroupRule(
            IpProtocol="tcp",
            FromPort=ApplicationPort,
            ToPort=ApplicationPort,
            CidrIp=myIP,
        ),
    ],
))
ud = Base64(Join('\n', [
  "#!/bin/bash",
  "yum install --enablerepo=epel -y git",
  "pip install --upgrade pip",
  "ln -s /usr/local/bin/pip /usr/bin/pip",
  "pip install ansible",
  AnsiblePullCmd,
  "echo '*/10 * * * * root {}' > /etc/cron.d/ansible.pull".format(AnsiblePullCmd)
]))

t.add_resource(IAMPolicy( 
    "Policy", 
    PolicyName="AllowS3", 
    PolicyDocument=Policy( 
        Statement=[ 
            Statement( 
                Effect=Allow,
		Action=[Action("s3", "*")], 
                Resource=["*"]) 
        ] 
    ), 
    Roles=[Ref("Role")] 
))

t.add_resource(Role(
    "Role",
    AssumeRolePolicyDocument=Policy(
        Statement=[
            Statement(
                Effect=Allow,
                Action=[AssumeRole],
                Principal=Principal("Service", ["ec2.amazonaws.com"])
            )
        ]
    )
))

t.add_resource(InstanceProfile( 
    "InstanceProfile", 
    Path="/", 
    Roles=[Ref("Role")] 
))

t.add_resource(LaunchConfiguration( 
    "LaunchConfiguration", 
    UserData=ud, 
    ImageId="ami-047bb4163c506cd98", 
    KeyName=Ref("KeyPair"),
    SecurityGroups=[Ref("SecurityGroup")], 
    InstanceType=Ref("InstanceType"), 
    IamInstanceProfile=Ref("InstanceProfile"), 
))

t.add_resource(AutoScalingGroup( 
    "AutoscalingGroup", 
    DesiredCapacity=Ref("ScaleCapacity"), 
    LaunchConfigurationName=Ref("LaunchConfiguration"),
    MinSize=1, 
    MaxSize=2,
    LoadBalancerNames=[Ref("LoadBalancer")], 
    VPCZoneIdentifier=Ref("PublicSubnet"), 
))

t.add_resource(ScalingPolicy( 
    "ScaleDownPolicy", 
    ScalingAdjustment="-1", 
    AutoScalingGroupName=Ref("AutoscalingGroup"), 
    AdjustmentType="ChangeInCapacity", 
)) 
 
t.add_resource(ScalingPolicy( 
    "ScaleUpPolicy", 
    ScalingAdjustment="1", 
    AutoScalingGroupName=Ref("AutoscalingGroup"), 
    AdjustmentType="ChangeInCapacity", 
))

t.add_resource(Alarm( 
    "CPUTooLow", 
    AlarmDescription="Alarm if CPU too low",
    Namespace="AWS/EC2", 
    MetricName="CPUUtilization",
    Dimensions=[ 
        MetricDimension( 
            Name="AutoScalingGroupName", 
            Value=Ref("AutoscalingGroup") 
        ), 
    ],
    Statistic="Average", 
    Period="60", 
    EvaluationPeriods="1", 
    Threshold="30", 
    ComparisonOperator="LessThanThreshold",
    AlarmActions=[Ref("ScaleDownPolicy")], 
))

t.add_resource(Alarm( 
    "CPUTooHigh", 
    AlarmDescription="Alarm if CPU too high", 
    Namespace="AWS/EC2", 
    MetricName="CPUUtilization", 
    Dimensions=[ 
        MetricDimension( 
            Name="AutoScalingGroupName", 
            Value=Ref("AutoscalingGroup") 
        ), 
    ], 
    Statistic="Average", 
    Period="60", 
    EvaluationPeriods="1", 
    Threshold="60", 
    ComparisonOperator="GreaterThanThreshold", 
    AlarmActions=[Ref("ScaleUpPolicy"), ], 
    InsufficientDataActions=[Ref("ScaleUpPolicy")], 
)) 

t.add_output(Output( 
    "WebUrl", 
    Description="Application endpoint", 
    Value=Join("", [ 
        "http://", GetAtt("LoadBalancer", "DNSName"), 
        ":", ApplicationPort 
    ]), 
)) 

print (t.to_json())
