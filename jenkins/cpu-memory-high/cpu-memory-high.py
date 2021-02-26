import boto3
import pprint
import re
import sys
import json
import datetime
import argparse


client = boto3.client('ecs', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1' )
ses = boto3.client('ses', region_name='us-east-1')

def get_all_clusters():
    token = ''
    clusterList = []
    while token is not None:
        if token == '':
            response = client.list_clusters(
            maxResults = 100
            )
        else:
            response = client.list_clusters(
            nextToken = token
            )
        clusterList += response['clusterArns']
        token = response.get('nextToken', None)
    return clusterList


def get_all_services_flushed(clusters):
    services = []
    for c in clusters:
        token = ''
        while token is not None:
            if token == '':
                response = client.list_services(cluster=c, maxResults=100)
            else:
                response = client.list_services(cluster=c, maxResults=100, nextToken=token)
            for s in response['serviceArns']:
                m = re.search(r'cluster/(.*)', c)
                cluster_name = m[1]
                service_name = s.split('/')[-1]
                services.append({"Cluster": cluster_name, "Service": service_name})
            token = response.get('nextToken', None)
    return services

def send_email(email_msg, email_subject):
    email_to = 'EMAIL HERE'
    email_source = 'EMAIL HERE'
    email_source_arn = 'ARN EMAIL HERE'
    ses.send_email(
        Destination={
            'ToAddresses': [email_to],
        },
        Message={
            'Body': {
                'Html': {
                    'Charset': 'UTF-8',
                    'Data': email_msg,
                },
            },
            'Subject': {
                'Charset': 'UTF-8',
                'Data': email_subject,
            },
        },
        Source=email_source,
        SourceArn=email_source_arn
    )
    print(f"\nInfo email sent to {email_to}!")


def relay_message(results_memory, results_cpu, percent_cpu, percent_mem, seconds_back_in_time):
    minutes = int(seconds_back_in_time) // 60
    email_subject = "Jenkins Job Info: Memory/CPU over ultilization"
    email_msg = "<html><h2>The following services went over threshold defined:<h2>"
    email_msg += '<h3>The criteria defined is to seek any services that that went over ' +  str(percent_cpu) + ' percent in CPU ultilization'
    email_msg += ' and/or any services that went over ' + str(percent_mem) + ' percent in memory ultilization ' 
    email_msg += 'in the past ' + str(minutes) +  ' minutes</h3>'
    if results_cpu:
        email_msg += '<table border="1"cellpadding="10"><tr><th>ECSCluster</th><th>Service</th><th>Average CPU Ultilization(Percent)</th>'
        for r in results_cpu:
            email_msg += '<tr>'
            email_msg += '<td>'
            email_msg += str(r['ECSCluster'])
            email_msg += '</td>'
            email_msg += '<td>'
            email_msg += str(r['Service'])
            email_msg += '</td>'
            email_msg += '<td>'
            email_msg += str(r['Average CPU Ultilization(Percent)'])
            email_msg += '</td>'
            email_msg += '</tr>'
        email_msg += '</table>'
    email_msg += '<br/>'
    if results_memory:
        email_msg += '<table border="1"cellpadding="10"><tr><th>ECSCluster</th><th>Service</th><th>Average Memory Ultilization(Percent)</th>'
        for r in results_memory:
            email_msg += '<tr>'
            email_msg += '<td>'
            email_msg += str(r['ECSCluster'])
            email_msg += '</td>'
            email_msg += '<td>'
            email_msg += str(r['Service'])
            email_msg += '</td>'
            email_msg += '<td>'
            email_msg += str(r['Average Memory Ultilization(Percent)'])
            email_msg += '</td>'
            email_msg += '</tr>'
        email_msg += '</table>'
    # email_msg =' </html>'
    send_email(email_msg, email_subject)

def main():
    print("its starting")
    parser = argparse.ArgumentParser()
    parser.add_argument('thresold_percent_cpu')
    parser.add_argument('thresold_percent_memory')
    parser.add_argument('seconds_back_in_time')
    args = parser.parse_args()
    percent_cpu = args.thresold_percent_cpu
    percent_mem = args.thresold_percent_memory
    seconds_back_in_time = args.seconds_back_in_time


    results_memory = []
    results_cpu = []
    print("Getting the clusters.....")
    clusters = get_all_clusters()
    print("Getting the services.....")
    services = get_all_services_flushed(clusters)

    for s in services:
        # 1800 secs = 30 mins
        response_memory = cloudwatch.get_metric_statistics(
                Period=300,
                StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=int(seconds_back_in_time)),
                EndTime=datetime.datetime.utcnow(),
                MetricName='MemoryUtilization',
                Namespace='AWS/ECS',
                Statistics=['Average'],
                Dimensions=[{'Name':'ClusterName', 'Value': s['Cluster']}, {'Name':'ServiceName', 'Value': s['Service']}])

        response_cpu = cloudwatch.get_metric_statistics(
            Period=300,
            StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=int(seconds_back_in_time)),
            EndTime=datetime.datetime.utcnow(),
            MetricName='CPUUtilization',
            Namespace='AWS/ECS',
            Statistics=['Average'],
            Dimensions=[{'Name':'ClusterName', 'Value': s['Cluster']}, {'Name':'ServiceName', 'Value': s['Service']}])

    
        if response_memory['Datapoints'] != []:
                average = response_memory['Datapoints'][0]['Average']
                if average >= int(percent_mem):
                    results_memory.append({'ECSCluster': s['Cluster'], "Service": s['Service'], "Average Memory Ultilization(Percent)": round(average)})

        if response_cpu['Datapoints'] != []:
                average = response_cpu['Datapoints'][0]['Average']
                if average >= int(percent_cpu):
                    results_cpu.append({'ECSCluster': s['Cluster'], "Service": s['Service'], "Average CPU Ultilization(Percent)": round(average)})

    if results_cpu or results_memory: 
        relay_message(results_memory, results_cpu, percent_cpu, percent_mem, seconds_back_in_time)

main()