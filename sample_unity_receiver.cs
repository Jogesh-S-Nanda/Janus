using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

public class DrakeReceiver : MonoBehaviour
{
    [Header("Network Settings")]
    public int port = 5005;

    // Threading controls
    private UdpClient udpClient;
    private Thread receiveThread;
    private bool isRunning = false;

    // Thread-safe data caching
    private readonly object lockObject = new object();
    private string latestJsonData = "";
    private bool hasNewData = false;

    // Structured data format container matching our Python payload
    [System.Serializable]
    public class DrakeRobotState
    {
        public float[] positions;
    }

    [Header("Robot References")]
    public Transform[] robotJointTransforms; // Assign your robot's Unity game objects here in order

    void Start()
    {
        // 1. Initialize and start the background listening thread
        udpClient = new UdpClient(port);
        isRunning = true;
        
        receiveThread = new Thread(new ThreadStart(ReceiveDataWorker));
        receiveThread.IsBackground = true;
        receiveThread.Start();
    }

    private void ReceiveDataWorker()
    {
        IPEndPoint remoteEndPoint = new IPEndPoint(IPAddress.Any, port);

        while (isRunning)
        {
            try
            {
                // Blocks until data arrives over the network socket
                byte[] receiveBytes = udpClient.Receive(ref remoteEndPoint);
                string text = Encoding.UTF8.GetString(receiveBytes);

                // Safely update shared memory using a thread lock
                lock (lockObject)
                {
                    latestJsonData = text;
                    hasNewData = true;
                }
            }
            catch (Exception ex)
            {
                // Suppress errors logged during app shutdown cleanup
                if (isRunning) Debug.LogError($"UDP Receive Error: {ex.Message}");
            }
        }
    }

    void Update()
    {
        string dataToParse = "";
        bool processThisFrame = false;

        // 2. Main thread checks if the network thread received updates
        lock (lockObject)
        {
            if (hasNewData)
            {
                dataToParse = latestJsonData;
                hasNewData = false;
                processThisFrame = true;
            }
        }

        // 3. Apply the positions to the visual robot bones
        if (processThisFrame && !string.IsNullOrEmpty(dataToParse))
        {
            try
            {
                DrakeRobotState state = JsonUtility.FromJson<DrakeRobotState>(dataToParse);

                // Safety check: ensure our received array matches our assigned transform array size
                int iterations = Mathf.Min(state.positions.Length, robotJointTransforms.Length);
                
                for (int i = 0; i < iterations; i++)
                {
                    if (robotJointTransforms[i] != null)
                    {
                        // Note: Converting Drake radians to Unity degrees 
                        float angleInDegrees = state.positions[i] * Mathf.Rad2Deg;

                        // Swap/invert axes here depending on your robot's joint axis (e.g., rotating around Y)
                        robotJointTransforms[i].localRotation = Quaternion.Euler(0, angleInDegrees, 0);
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"JSON Parsing Error: {ex.Message}");
            }
        }
    }

    private void OnDisable()
    {
        // 4. Force-quit thread loops when editing or closing the application
        isRunning = false;
        if (udpClient != null)
        {
            udpClient.Close();
        }
        if (receiveThread != null && receiveThread.IsAlive)
        {
            receiveThread.Abort();
        }
    }
}
