"""Generating CloudFormation template."""

from ipaddress import ip_network
from ipify import get_ip

from troposphere import (
    Base64,
    ec2,
    GetAtt,
    Join,
    Output,
    Parameter,
    Ref,
    Template,
)

from troposphere.iam import (
    InstanceProfile,
    PolicyType as IAMPolicy,
    Role,
)

from awacs.aws import (
    Action,
    Allow,
    Policy,
    Principal,
    Statement,
)

from awacs.sts import AssumeRole

ApplicatioName = "jenkins"
ApplicationPort = "8080"

GithubAccount = "chilliblast"
GithubAnsibleURL = "https://github.com/{}/Ansible".format(GithubAccount)

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

t.add_resource(ec2.SecurityGroup(
    "SecurityGroup",
    GroupDescription="Allow SSH and TCP/{} access".format(ApplicationPort),
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
  "ln -s /usr/local/bin/pip pip",
  "pip install --upgrade pip",
  "pip install ansible",
  AnsiblePullCmd,
  "echo '*/10 * * * * root {}' > /etc/cron.d/ansible.pull".format(AnsiblePullCmd)
]))

t.add_resource(ec2.Instance(
    "instance",
    ImageId=AMI_image,
    InstanceType="t2.micro",
    SecurityGroups=[Ref("SecurityGroup")],
    KeyName=Ref("KeyPair"),
    UserData=ud,
    IamInstanceProfile=Ref("InstanceProfile"),
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

t.add_output(Output(
    "InstancePublicIp",
    Description="Public IP of our instance.",
    Value=GetAtt("instance", "PublicIp"),
))

t.add_output(Output(
    "WebUrl",
    Description="Application endpoint",
    Value=Join("", [
        "http://", GetAtt("instance", "PublicDnsName"),
        ":", ApplicationPort
    ]),
))

print t.to_json()
